"""
Audio utilities — cropping, conversion, format detection.
Uses imageio-ffmpeg bundled binary when system ffmpeg is not available.
"""

import os
import subprocess
import sys
import logging

logger = logging.getLogger("debategraph.transcription")


def get_ffmpeg_path() -> str:
    """Get ffmpeg binary path — prefer imageio-ffmpeg (bundled), then system ffmpeg."""
    # 1. Try imageio-ffmpeg first (bundled binary, no system install needed)
    try:
        import imageio_ffmpeg
        path = imageio_ffmpeg.get_ffmpeg_exe()
        if path and os.path.exists(path):
            logger.debug(f"Using bundled ffmpeg: {path}")
            return path
    except ImportError:
        pass

    # 2. Try system ffmpeg in PATH
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            return "ffmpeg"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Helpful error: use the same Python that runs the server so the package goes into venv
    pip_cmd = f'"{sys.executable}" -m pip install imageio-ffmpeg'
    raise RuntimeError(
        "ffmpeg not found. Install with the same Python that runs the server so it goes into your venv:\n"
        f"  {pip_cmd}\n"
        "Or install system ffmpeg and add it to PATH."
    )


def crop_audio(
    input_path: str,
    output_path: str,
    start_seconds: float,
    duration_seconds: float,
) -> str:
    """
    Crop an audio file to a specific time range.
    
    Args:
        input_path: Path to input audio file
        output_path: Path for output file
        start_seconds: Start time in seconds
        duration_seconds: Duration in seconds
    
    Returns:
        Path to the cropped file
    """
    ffmpeg = get_ffmpeg_path()
    
    cmd = [
        ffmpeg,
        "-i", input_path,
        "-ss", str(start_seconds),
        "-t", str(duration_seconds),
        "-acodec", "libmp3lame",
        "-ab", "128k",
        "-y",
        output_path,
    ]
    
    logger.info(f"Cropping audio: {start_seconds}s to {start_seconds + duration_seconds}s")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    
    if result.returncode != 0:
        logger.error(f"ffmpeg crop failed: {result.stderr[:500]}")
        raise RuntimeError(f"ffmpeg crop failed: {result.stderr[:200]}")
    
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    logger.info(f"Cropped audio saved: {output_path} ({size_mb:.1f} MB)")
    return output_path


def _is_video_file(path: str) -> bool:
    """True if the file is a video format (has video stream to skip)."""
    ext = os.path.splitext(path)[1].lower()
    return ext in {".mp4", ".webm", ".avi", ".mkv", ".mov", ".flv"}


def convert_to_wav(input_path: str, output_path: str = None) -> str:
    """
    Convert audio/video to WAV 16kHz mono (optimal for Whisper).
    
    Args:
        input_path: Path to input file
        output_path: Path for output WAV. If None, replaces extension.
    
    Returns:
        Path to the WAV file
    """
    if input_path.endswith(".wav"):
        return input_path
    
    if output_path is None:
        output_path = os.path.splitext(input_path)[0] + ".wav"
    
    # Use absolute path to avoid Windows/OneDrive path issues
    input_path = os.path.abspath(input_path)
    output_path = os.path.abspath(output_path)
    
    ffmpeg = get_ffmpeg_path()
    
    cmd = [
        ffmpeg,
        "-i", input_path,
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        "-y",
        output_path,
    ]
    # For video files, skip video stream (extract audio only)
    if _is_video_file(input_path):
        cmd.insert(3, "-vn")  # -vn after -i input_path
    
    logger.info(f"Converting to WAV: {input_path} -> {output_path}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    
    if result.returncode != 0:
        # ffmpeg prints version banner first; actual error is usually at the end
        err_lines = result.stderr.strip().split("\n")
        err_tail = "\n".join(err_lines[-8:]) if len(err_lines) > 8 else result.stderr
        logger.error(f"ffmpeg convert failed: {err_tail}")
        raise RuntimeError(f"ffmpeg conversion failed: {err_tail}")
    
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    logger.info(f"WAV saved: {output_path} ({size_mb:.1f} MB)")
    return output_path


def get_audio_duration(input_path: str) -> float:
    """Get duration of an audio file in seconds."""
    ffmpeg = get_ffmpeg_path()
    # Use ffprobe if available, otherwise parse ffmpeg output
    ffprobe = ffmpeg.replace("ffmpeg", "ffprobe") if "ffmpeg" in ffmpeg else "ffprobe"
    
    try:
        cmd = [
            ffprobe,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            input_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    
    # Fallback: use ffmpeg to get duration
    cmd = [ffmpeg, "-i", input_path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    # Parse "Duration: HH:MM:SS.ms" from stderr
    for line in result.stderr.split("\n"):
        if "Duration:" in line:
            time_str = line.split("Duration:")[1].split(",")[0].strip()
            parts = time_str.split(":")
            if len(parts) == 3:
                h, m, s = parts
                return float(h) * 3600 + float(m) * 60 + float(s)
    
    return 0.0
