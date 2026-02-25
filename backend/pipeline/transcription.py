"""
Transcription pipeline using OpenAI gpt-4o-transcribe-diarize API.
Provides high-quality speech-to-text with built-in speaker diarization.

Model: gpt-4o-transcribe-diarize
- Transcription + speaker diarization in one API call
- Returns diarized_json with speaker labels, start/end timestamps
- Chunking: for audio > ~2 min or > 25 MB we split into 2-min chunks to avoid 500/timeouts
- File limit: 25 MB per request; long audio must be sent in chunks

Real-time / streaming: For true real-time diarization (e.g. live mic or stream),
OpenAI's Realtime API (WebSocket) supports transcription-only sessions with
gpt-4o-transcribe / gpt-4o-transcribe-diarize and delta events. See:
https://platform.openai.com/docs/guides/realtime-transcription
"""

import os
import asyncio
import logging
from pathlib import Path
from typing import Optional

from api.models.schemas import TranscriptionResult, TranscriptionSegment
from config.settings import STT_MODEL, STT_PROMPT

logger = logging.getLogger("debategraph.transcription")

# Try to import OpenAI
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("openai package not installed. pip install openai")


def transcribe_audio(
    audio_path: str,
    num_speakers: Optional[int] = None,
    language: Optional[str] = None,
) -> TranscriptionResult:
    """
    Transcribe an audio file with speaker diarization using OpenAI API.

    Uses gpt-4o-transcribe-diarize for combined transcription + diarization.
    Falls back to gpt-4o-transcribe (without diarization) if diarize model fails.

    Args:
        audio_path: Path to audio file (mp3, wav, mp4, webm, etc.)
        num_speakers: Expected number of speakers (not used by OpenAI API, kept for interface compat)
        language: Language code (optional, auto-detected if not provided)

    Returns:
        TranscriptionResult with timestamped, speaker-attributed segments
    """
    api_key = os.getenv("OPENAI_API_KEY", "")

    if not OPENAI_AVAILABLE:
        logger.error("OpenAI package not installed. Cannot transcribe.")
        raise RuntimeError("OpenAI package not installed. Run: pip install openai")

    if not api_key:
        logger.error("OPENAI_API_KEY not set in environment. Cannot transcribe.")
        raise RuntimeError("OPENAI_API_KEY not set. Add it to your .env file.")

    # Validate file exists and size
    file_path = Path(audio_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    file_size_mb = file_path.stat().st_size / (1024 * 1024)
    logger.info(f"Transcribing: {file_path.name} ({file_size_mb:.1f} MB)")

    # OpenAI requires chunking for gpt-4o-transcribe-diarize when audio > 30s; large single requests often 500.
    # Use chunked transcription for: size > 25 MB OR estimated duration > 2 min (safe threshold).
    CHUNK_SIZE_MB = 25
    CHUNK_DURATION_ESTIMATE_MIN = 2  # assume ~1 MB per min for WAV; use chunked if we might exceed safe length
    use_chunked = file_size_mb > CHUNK_SIZE_MB or file_size_mb > (CHUNK_DURATION_ESTIMATE_MIN * 1.5)
    if use_chunked:
        logger.info(
            f"File {file_size_mb:.1f} MB exceeds safe single-request size/duration. Using chunked transcription."
        )
        return _transcribe_chunked(audio_path, api_key, language)

    # Try diarized transcription first (single request)
    try:
        return _transcribe_diarized(audio_path, api_key, language)
    except Exception as e:
        logger.warning(f"Diarized transcription failed: {e}. Falling back to standard transcription.")
        return _transcribe_standard(audio_path, api_key, language)


def _transcribe_diarized(
    audio_path: str,
    api_key: str,
    language: Optional[str] = None,
) -> TranscriptionResult:
    """
    Transcribe with speaker diarization using gpt-4o-transcribe-diarize.
    Returns segments with speaker labels.
    """
    client = OpenAI(api_key=api_key)
    model = STT_MODEL  # "gpt-4o-transcribe-diarize"

    logger.info(f"Using model: {model} (diarized mode)")

    with open(audio_path, "rb") as audio_file:
        # Build API call kwargs
        kwargs = {
            "model": model,
            "file": audio_file,
            "response_format": "diarized_json",
            "chunking_strategy": "auto",
        }

        # Language hint if provided
        if language:
            kwargs["language"] = language

        logger.info("Sending audio to OpenAI API (diarized)...")
        transcript = client.audio.transcriptions.create(**kwargs)

    # Parse diarized response
    segments = []
    speakers_seen = set()

    logger.info(f"Received diarized transcript")

    # The diarized_json response has a 'segments' attribute with speaker info
    if hasattr(transcript, 'segments') and transcript.segments:
        for seg in transcript.segments:
            speaker = getattr(seg, 'speaker', 'SPEAKER_00') or 'SPEAKER_00'
            text = getattr(seg, 'text', '').strip()
            start = getattr(seg, 'start', 0.0)
            end = getattr(seg, 'end', 0.0)

            if not text:
                continue

            # Normalize speaker name to SPEAKER_XX format
            speaker_normalized = _normalize_speaker(speaker)
            speakers_seen.add(speaker_normalized)

            segments.append(TranscriptionSegment(
                speaker=speaker_normalized,
                text=text,
                start=round(float(start), 2),
                end=round(float(end), 2),
            ))

        logger.info(f"Parsed {len(segments)} diarized segments, {len(speakers_seen)} speakers")
    else:
        # Fallback: if no segments, try to get plain text
        text = getattr(transcript, 'text', '')
        if text:
            logger.warning("No diarized segments found, using plain text")
            segments.append(TranscriptionSegment(
                speaker="SPEAKER_00",
                text=text.strip(),
                start=0.0,
                end=0.0,
            ))
            speakers_seen.add("SPEAKER_00")

    if not segments:
        raise RuntimeError("No transcription segments returned from API")

    # Detect language from response or default
    detected_language = language or "en"

    result = TranscriptionResult(
        segments=segments,
        language=detected_language,
        num_speakers=len(speakers_seen),
    )

    logger.info(f"Transcription complete: {len(segments)} segments, "
                f"{len(speakers_seen)} speakers, language={detected_language}")

    # Log first few segments for debugging
    for i, seg in enumerate(segments[:5]):
        logger.debug(f"  [{seg.start:.1f}s-{seg.end:.1f}s] {seg.speaker}: {seg.text[:80]}...")

    return result


def _transcribe_standard(
    audio_path: str,
    api_key: str,
    language: Optional[str] = None,
) -> TranscriptionResult:
    """
    Fallback: transcribe without diarization using gpt-4o-transcribe.
    All text attributed to SPEAKER_00.
    """
    client = OpenAI(api_key=api_key)
    model = "gpt-4o-transcribe"

    logger.info(f"Using model: {model} (standard mode, no diarization)")

    with open(audio_path, "rb") as audio_file:
        kwargs = {
            "model": model,
            "file": audio_file,
            "response_format": "json",
        }

        if language:
            kwargs["language"] = language

        # Add prompt for debate context
        if STT_PROMPT:
            kwargs["prompt"] = STT_PROMPT

        logger.info("Sending audio to OpenAI API (standard)...")
        transcript = client.audio.transcriptions.create(**kwargs)

    text = transcript.text.strip() if hasattr(transcript, 'text') else ""

    if not text:
        raise RuntimeError("Empty transcription returned from API")

    # Split into segments by sentences (rough approximation)
    segments = _split_text_into_segments(text)

    logger.info(f"Standard transcription: {len(segments)} segments (single speaker)")

    return TranscriptionResult(
        segments=segments,
        language=language or "en",
        num_speakers=1,
    )


def _transcribe_chunked(
    audio_path: str,
    api_key: str,
    language: Optional[str] = None,
) -> TranscriptionResult:
    """
    Split audio into short chunks (2 min), transcribe each with diarization, then merge.
    Avoids 500 errors and timeouts from sending long audio in one request.
    OpenAI recommends chunking for gpt-4o-transcribe-diarize when input > 30 seconds.
    """
    try:
        from pydub import AudioSegment
    except ImportError:
        raise RuntimeError("pydub required for chunked transcription. pip install pydub")

    # pydub looks for ffmpeg in PATH; we inject our path (imageio-ffmpeg or system) so export() works
    from utils.audio import get_ffmpeg_path
    AudioSegment.converter = get_ffmpeg_path()

    logger.info("Splitting audio into chunks for safe API requests...")

    audio = AudioSegment.from_file(audio_path)
    # 2 minutes per chunk: keeps each request well under limits and avoids 500/timeouts
    chunk_duration_ms = 2 * 60 * 1000
    chunks = []

    for i in range(0, len(audio), chunk_duration_ms):
        chunk = audio[i:i + chunk_duration_ms]
        chunk_idx = i // chunk_duration_ms
        chunk_path = f"{audio_path}.chunk_{chunk_idx}.mp3"
        chunk.export(chunk_path, format="mp3")
        chunks.append((chunk_path, i / 1000.0))  # (path, offset_seconds)

    logger.info(f"Split into {len(chunks)} chunks (~2 min each)")

    all_segments = []
    speakers_seen = set()

    for chunk_path, offset in chunks:
        try:
            result = _transcribe_diarized(chunk_path, api_key, language)
            for seg in result.segments:
                seg.start += offset
                seg.end += offset
                all_segments.append(seg)
                speakers_seen.add(seg.speaker)
        except Exception as e:
            logger.error(f"Chunk transcription failed: {e}")
        finally:
            # Clean up chunk file
            try:
                os.remove(chunk_path)
            except OSError:
                pass

    return TranscriptionResult(
        segments=all_segments,
        language=language or "en",
        num_speakers=len(speakers_seen),
    )


def _normalize_speaker(speaker: str) -> str:
    """
    Normalize speaker labels to SPEAKER_XX format.
    OpenAI may return labels like 'speaker_0', 'Speaker 1', 'SPEAKER_00', etc.
    """
    if not speaker:
        return "SPEAKER_00"

    # Already in correct format
    if speaker.startswith("SPEAKER_") and speaker[8:].isdigit():
        return speaker

    # Extract number from various formats
    import re
    match = re.search(r'(\d+)', speaker)
    if match:
        num = int(match.group(1))
        return f"SPEAKER_{num:02d}"

    # Hash-based fallback for named speakers
    return f"SPEAKER_{abs(hash(speaker)) % 100:02d}"


def _transcribe_demo(demo_id: str = "demo") -> TranscriptionResult:
    """
    Return a small hardcoded transcription for demo/testing purposes.
    Allows the frontend to work without any API keys or audio files.
    """
    logger.info(f"Generating demo transcription (id={demo_id})")
    segments = [
        TranscriptionSegment(speaker="SPEAKER_00", text="I believe we need to invest more in education to ensure every child has access to quality schools.", start=0.0, end=6.5),
        TranscriptionSegment(speaker="SPEAKER_01", text="While education is important, we can't just throw money at the problem. We need accountability and results.", start=7.0, end=13.0),
        TranscriptionSegment(speaker="SPEAKER_00", text="Studies show that increased funding directly correlates with better student outcomes.", start=13.5, end=19.0),
        TranscriptionSegment(speaker="SPEAKER_01", text="That's a hasty generalization. The data is more nuanced than that.", start=19.5, end=24.0),
        TranscriptionSegment(speaker="SPEAKER_00", text="If we don't act now, an entire generation will be left behind.", start=24.5, end=29.0),
        TranscriptionSegment(speaker="SPEAKER_01", text="That's a slippery slope argument. There are many factors at play.", start=29.5, end=34.0),
        TranscriptionSegment(speaker="SPEAKER_00", text="My opponent clearly doesn't care about children's futures.", start=34.5, end=39.0),
        TranscriptionSegment(speaker="SPEAKER_01", text="That's an ad hominem attack. I care deeply, I just disagree on the approach.", start=39.5, end=45.0),
        TranscriptionSegment(speaker="SPEAKER_00", text="The National Education Association supports our plan.", start=45.5, end=50.0),
        TranscriptionSegment(speaker="SPEAKER_01", text="Appeal to authority doesn't make the plan effective. Let's look at the evidence.", start=50.5, end=56.0),
    ]
    return TranscriptionResult(
        segments=segments,
        language="en",
        num_speakers=2,
    )


def _split_text_into_segments(
    text: str,
    max_segment_duration: float = 15.0,
) -> list[TranscriptionSegment]:
    """
    Split plain text into approximate segments (for non-diarized fallback).
    """
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text)

    segments = []
    current_time = 0.0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # Estimate duration: ~150 words per minute
        word_count = len(sentence.split())
        duration = max(1.0, (word_count / 150) * 60)

        segments.append(TranscriptionSegment(
            speaker="SPEAKER_00",
            text=sentence,
            start=round(current_time, 2),
            end=round(current_time + duration, 2),
        ))
        current_time += duration + 0.5  # small gap between segments

    return segments
