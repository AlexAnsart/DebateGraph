"""
Audio chunking module for real-time streaming (Phase 3).
Splits audio stream into overlapping windows for incremental processing.
"""

import logging
import numpy as np
from typing import Generator, Optional

logger = logging.getLogger(__name__)

# Default chunking parameters from spec
DEFAULT_CHUNK_DURATION = 5.0   # seconds
DEFAULT_OVERLAP = 1.0          # seconds
SAMPLE_RATE = 16000            # 16kHz mono


class AudioChunker:
    """
    Splits a continuous audio stream into overlapping chunks
    suitable for incremental STT processing.

    Phase 3: Will receive audio from Web Audio API via WebSocket.
    Currently supports file-based chunking for testing.
    """

    def __init__(
        self,
        chunk_duration: float = DEFAULT_CHUNK_DURATION,
        overlap: float = DEFAULT_OVERLAP,
        sample_rate: int = SAMPLE_RATE,
    ):
        self.chunk_duration = chunk_duration
        self.overlap = overlap
        self.sample_rate = sample_rate
        self.chunk_samples = int(chunk_duration * sample_rate)
        self.overlap_samples = int(overlap * sample_rate)
        self.step_samples = self.chunk_samples - self.overlap_samples
        self.buffer = np.array([], dtype=np.float32)
        self.total_samples_processed = 0

    def feed(self, audio_data: np.ndarray) -> list[dict]:
        """
        Feed new audio data into the chunker.

        Args:
            audio_data: numpy array of audio samples (float32, mono, 16kHz)

        Returns:
            List of chunk dicts with keys: audio, start_time, end_time, chunk_index
        """
        self.buffer = np.concatenate([self.buffer, audio_data])
        chunks = []

        while len(self.buffer) >= self.chunk_samples:
            chunk_audio = self.buffer[:self.chunk_samples]
            start_sample = self.total_samples_processed
            end_sample = start_sample + self.chunk_samples

            chunks.append({
                "audio": chunk_audio,
                "start_time": start_sample / self.sample_rate,
                "end_time": end_sample / self.sample_rate,
                "chunk_index": len(chunks),
            })

            self.buffer = self.buffer[self.step_samples:]
            self.total_samples_processed += self.step_samples

        return chunks

    def flush(self) -> Optional[dict]:
        """
        Flush remaining audio in the buffer as a final chunk.

        Returns:
            Final chunk dict or None if buffer is empty
        """
        if len(self.buffer) == 0:
            return None

        start_sample = self.total_samples_processed
        end_sample = start_sample + len(self.buffer)

        chunk = {
            "audio": self.buffer.copy(),
            "start_time": start_sample / self.sample_rate,
            "end_time": end_sample / self.sample_rate,
            "chunk_index": -1,  # indicates final chunk
        }

        self.buffer = np.array([], dtype=np.float32)
        self.total_samples_processed = end_sample

        return chunk

    def reset(self):
        """Reset the chunker state."""
        self.buffer = np.array([], dtype=np.float32)
        self.total_samples_processed = 0


def chunk_audio_file(
    audio_path: str,
    chunk_duration: float = DEFAULT_CHUNK_DURATION,
    overlap: float = DEFAULT_OVERLAP,
) -> Generator[dict, None, None]:
    """
    Generator that yields overlapping chunks from an audio file.
    Useful for testing the streaming pipeline with file input.

    Args:
        audio_path: Path to WAV file
        chunk_duration: Duration of each chunk in seconds
        overlap: Overlap between consecutive chunks in seconds

    Yields:
        Chunk dicts with audio data and timing info
    """
    try:
        import wave
        with wave.open(audio_path, "rb") as wf:
            assert wf.getnchannels() == 1, "Expected mono audio"
            assert wf.getsampwidth() == 2, "Expected 16-bit audio"
            sr = wf.getframerate()

            chunker = AudioChunker(chunk_duration, overlap, sr)
            read_size = int(sr * 0.5)  # read 0.5s at a time

            while True:
                frames = wf.readframes(read_size)
                if not frames:
                    break
                audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                for chunk in chunker.feed(audio):
                    yield chunk

            final = chunker.flush()
            if final:
                yield final

    except Exception as e:
        logger.error(f"Error chunking audio file: {e}")
        raise
