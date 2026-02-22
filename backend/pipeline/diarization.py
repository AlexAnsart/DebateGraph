"""
Speaker diarization module using pyannote.audio.
Handles speaker segmentation independently from WhisperX when needed.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import pyannote
try:
    from pyannote.audio import Pipeline as PyannotePipeline
    PYANNOTE_AVAILABLE = True
except ImportError:
    PYANNOTE_AVAILABLE = False
    logger.warning("pyannote.audio not installed. Diarization unavailable standalone.")


class SpeakerDiarizer:
    """
    Standalone speaker diarization using pyannote/speaker-diarization-community-1.
    Used when WhisperX is not available or for real-time mode (Phase 3).
    """

    def __init__(self):
        self.pipeline = None
        self.device = "cpu"

    def load(self, device: str = "auto"):
        """Load the pyannote diarization pipeline."""
        if not PYANNOTE_AVAILABLE:
            logger.error("pyannote.audio is not installed")
            return

        if device == "auto":
            try:
                import torch
                self.device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                self.device = "cpu"
        else:
            self.device = device

        hf_token = os.getenv("HUGGINGFACE_TOKEN", "")

        try:
            self.pipeline = PyannotePipeline.from_pretrained(
                "pyannote/speaker-diarization-community-1",
                use_auth_token=hf_token,
            )
            if self.device == "cuda":
                import torch
                self.pipeline.to(torch.device("cuda"))
            logger.info(f"Pyannote diarization pipeline loaded on {self.device}")
        except Exception as e:
            logger.error(f"Failed to load pyannote pipeline: {e}")
            self.pipeline = None

    def diarize(
        self,
        audio_path: str,
        num_speakers: Optional[int] = None,
    ) -> list[dict]:
        """
        Run speaker diarization on an audio file.

        Args:
            audio_path: Path to audio file
            num_speakers: Expected number of speakers (None = auto)

        Returns:
            List of dicts with keys: speaker, start, end
        """
        if self.pipeline is None:
            logger.warning("Diarization pipeline not loaded, returning single speaker")
            return [{"speaker": "SPEAKER_00", "start": 0.0, "end": 999999.0}]

        kwargs = {}
        if num_speakers is not None:
            kwargs["num_speakers"] = num_speakers

        try:
            diarization = self.pipeline(audio_path, **kwargs)

            segments = []
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                segments.append({
                    "speaker": speaker,
                    "start": round(turn.start, 2),
                    "end": round(turn.end, 2),
                })

            logger.info(f"Diarization complete: {len(segments)} segments, "
                        f"{len(set(s['speaker'] for s in segments))} speakers")
            return segments

        except Exception as e:
            logger.error(f"Diarization failed: {e}")
            return [{"speaker": "SPEAKER_00", "start": 0.0, "end": 999999.0}]


# Module-level singleton
_diarizer: Optional[SpeakerDiarizer] = None


def get_diarizer() -> SpeakerDiarizer:
    """Get or create the singleton diarizer instance."""
    global _diarizer
    if _diarizer is None:
        _diarizer = SpeakerDiarizer()
    return _diarizer
