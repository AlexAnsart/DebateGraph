"""
Transcription pipeline using WhisperX (faster-whisper + pyannote diarization).
Falls back to a demo/mock mode if WhisperX is not installed.
"""

import os
import logging
from typing import Optional

from api.models.schemas import TranscriptionResult, TranscriptionSegment

logger = logging.getLogger(__name__)

# Try to import WhisperX; fall back gracefully
try:
    import whisperx
    WHISPERX_AVAILABLE = True
    logger.info("WhisperX is available")
except ImportError:
    WHISPERX_AVAILABLE = False
    logger.warning("WhisperX not installed. Using demo transcription mode.")


def get_whisper_config() -> dict:
    """Read Whisper configuration from environment variables."""
    return {
        "model": os.getenv("WHISPER_MODEL", "medium"),
        "device": os.getenv("WHISPER_DEVICE", "auto"),
        "compute_type": os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
    }


def _resolve_device(device_str: str) -> str:
    """Resolve 'auto' device to 'cuda' or 'cpu'."""
    if device_str == "auto":
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"
    return device_str


def transcribe_audio(
    audio_path: str,
    num_speakers: Optional[int] = None,
    language: Optional[str] = None,
) -> TranscriptionResult:
    """
    Transcribe an audio file with speaker diarization.

    Uses WhisperX if available, otherwise returns demo data.

    Args:
        audio_path: Path to WAV audio file (16kHz mono recommended)
        num_speakers: Expected number of speakers (None = auto-detect)
        language: Language code (None = auto-detect)

    Returns:
        TranscriptionResult with timestamped, speaker-attributed segments
    """
    if WHISPERX_AVAILABLE:
        return _transcribe_whisperx(audio_path, num_speakers, language)
    else:
        return _transcribe_demo(audio_path)


def _transcribe_whisperx(
    audio_path: str,
    num_speakers: Optional[int] = None,
    language: Optional[str] = None,
) -> TranscriptionResult:
    """Full WhisperX pipeline: STT + alignment + diarization."""
    config = get_whisper_config()
    device = _resolve_device(config["device"])
    compute_type = config["compute_type"]

    # Adjust compute type for CPU
    if device == "cpu" and compute_type == "float16":
        compute_type = "int8"

    hf_token = os.getenv("HUGGINGFACE_TOKEN", "")

    logger.info(f"Loading WhisperX model '{config['model']}' on {device} ({compute_type})")

    # Step 1: Load model and transcribe
    model = whisperx.load_model(
        config["model"],
        device,
        compute_type=compute_type,
        language=language,
    )

    audio = whisperx.load_audio(audio_path)
    result = model.transcribe(audio, batch_size=16)

    detected_language = result.get("language", language or "unknown")
    logger.info(f"Detected language: {detected_language}")

    # Step 2: Align whisper output for accurate timestamps
    try:
        model_a, metadata = whisperx.load_align_model(
            language_code=detected_language, device=device
        )
        result = whisperx.align(
            result["segments"], model_a, metadata, audio, device,
            return_char_alignments=False,
        )
    except Exception as e:
        logger.warning(f"Alignment failed (non-critical): {e}")

    # Step 3: Speaker diarization
    try:
        diarize_model = whisperx.DiarizationPipeline(
            use_auth_token=hf_token, device=device
        )
        diarize_kwargs = {}
        if num_speakers is not None:
            diarize_kwargs["num_speakers"] = num_speakers

        diarize_segments = diarize_model(audio_path, **diarize_kwargs)
        result = whisperx.assign_word_speakers(diarize_segments, result)
    except Exception as e:
        logger.warning(f"Diarization failed: {e}. Assigning all to SPEAKER_00.")

    # Build result
    segments = []
    speakers_seen = set()

    for seg in result.get("segments", []):
        speaker = seg.get("speaker", "SPEAKER_00")
        speakers_seen.add(speaker)
        segments.append(TranscriptionSegment(
            speaker=speaker,
            text=seg.get("text", "").strip(),
            start=round(seg.get("start", 0.0), 2),
            end=round(seg.get("end", 0.0), 2),
        ))

    return TranscriptionResult(
        segments=segments,
        language=detected_language,
        num_speakers=len(speakers_seen),
    )


def _transcribe_demo(audio_path: str) -> TranscriptionResult:
    """
    Demo transcription for development/testing without WhisperX.
    Returns a realistic mock debate transcription.
    """
    logger.info(f"[DEMO MODE] Generating mock transcription for: {audio_path}")

    demo_segments = [
        TranscriptionSegment(
            speaker="SPEAKER_00",
            text="I believe that artificial intelligence will fundamentally transform the job market within the next decade. Studies from MIT and Oxford show that up to 47% of jobs are at risk of automation.",
            start=0.0,
            end=12.5,
        ),
        TranscriptionSegment(
            speaker="SPEAKER_01",
            text="That 47% figure from the Oxford study has been widely criticized. The OECD revised it down to 14%. You're cherry-picking the most alarming statistic.",
            start=13.0,
            end=22.0,
        ),
        TranscriptionSegment(
            speaker="SPEAKER_00",
            text="Even if we take the OECD's more conservative estimate, 14% of jobs is still millions of people. And that doesn't account for the jobs that will be significantly transformed rather than eliminated.",
            start=22.5,
            end=34.0,
        ),
        TranscriptionSegment(
            speaker="SPEAKER_01",
            text="But every technological revolution has created more jobs than it destroyed. The industrial revolution, the computer revolution — people always predict doom and it never happens.",
            start=34.5,
            end=45.0,
        ),
        TranscriptionSegment(
            speaker="SPEAKER_00",
            text="That's a false analogy. Previous revolutions augmented human physical labor. AI is different because it targets cognitive tasks — the very thing that made humans irreplaceable before.",
            start=45.5,
            end=57.0,
        ),
        TranscriptionSegment(
            speaker="SPEAKER_01",
            text="You're just fear-mongering. People who oppose technological progress always end up on the wrong side of history. Are you suggesting we should stop developing AI?",
            start=57.5,
            end=67.0,
        ),
        TranscriptionSegment(
            speaker="SPEAKER_00",
            text="I never said we should stop developing AI. I said we need to prepare for its impact on employment. That's a completely different position, and you're misrepresenting my argument.",
            start=67.5,
            end=78.0,
        ),
        TranscriptionSegment(
            speaker="SPEAKER_01",
            text="Fine, but if we start regulating AI too heavily, companies will just move overseas, and then we'll lose both the jobs AND the technology. It's either full speed ahead or total decline.",
            start=78.5,
            end=90.0,
        ),
        TranscriptionSegment(
            speaker="SPEAKER_00",
            text="That's a false dilemma. There's a wide spectrum between no regulation and heavy regulation. Countries like the EU are finding middle ground with the AI Act.",
            start=90.5,
            end=101.0,
        ),
        TranscriptionSegment(
            speaker="SPEAKER_01",
            text="The EU AI Act is already being criticized by researchers as too restrictive. And besides, regulation always stifles innovation. Look at what happened to European tech companies compared to American ones.",
            start=101.5,
            end=114.0,
        ),
    ]

    return TranscriptionResult(
        segments=demo_segments,
        language="en",
        num_speakers=2,
    )
