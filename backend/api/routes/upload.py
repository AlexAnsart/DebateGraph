"""
Upload endpoint for audio/video files.
Handles file reception, conversion to WAV, and triggers the analysis pipeline.
"""

import os
import uuid
import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from api.models.schemas import (
    UploadResponse,
    AnalysisStatus,
    AnalysisSettings,
    GraphSnapshot,
)
from pipeline.transcription import transcribe_audio
from agents.orchestrator import run_analysis_pipeline
from graph.store import DebateGraphStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["upload"])

# In-memory job store (replace with Redis in production)
jobs: dict[str, AnalysisStatus] = {}

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".mp3", ".wav", ".mp4", ".webm", ".ogg", ".flac", ".m4a", ".avi", ".mkv"}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """
    Upload an audio or video file for analysis.
    The file is saved, converted to WAV if needed, and the analysis pipeline
    is launched as a background task.
    """
    # Validate file extension
    ext = Path(file.filename or "unknown.wav").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Generate job ID and save file
    job_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{job_id}{ext}"

    try:
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large (max 500 MB)")
        with open(file_path, "wb") as f:
            f.write(content)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save file")

    # Initialize job status
    jobs[job_id] = AnalysisStatus(
        job_id=job_id,
        status="processing",
        progress=0.0,
    )

    # Launch analysis pipeline in background
    background_tasks.add_task(process_file, job_id, str(file_path))

    return UploadResponse(
        job_id=job_id,
        status="processing",
        message=f"File '{file.filename}' uploaded successfully. Analysis started.",
    )


async def process_file(job_id: str, file_path: str):
    """
    Background task: runs the full analysis pipeline on an uploaded file.
    Updates the job status at each stage.
    """
    try:
        # Stage 1: Convert to WAV if needed
        jobs[job_id].status = "transcribing"
        jobs[job_id].progress = 0.1
        logger.info(f"[{job_id}] Starting transcription...")

        wav_path = await convert_to_wav(file_path)

        # Stage 2: Transcription + Diarization
        jobs[job_id].progress = 0.2
        transcription = await asyncio.to_thread(transcribe_audio, wav_path)
        jobs[job_id].transcription = transcription
        jobs[job_id].progress = 0.5
        logger.info(f"[{job_id}] Transcription complete: {len(transcription.segments)} segments")

        # Stage 3-5: Claim extraction + Graph construction + Analysis
        jobs[job_id].status = "extracting"
        jobs[job_id].progress = 0.6

        graph_store = DebateGraphStore()
        graph_snapshot = await run_analysis_pipeline(
            transcription, graph_store, session_id=job_id
        )

        jobs[job_id].status = "complete"
        jobs[job_id].progress = 1.0
        jobs[job_id].graph = graph_snapshot
        logger.info(f"[{job_id}] Analysis complete")

    except Exception as e:
        logger.error(f"[{job_id}] Pipeline error: {e}", exc_info=True)
        jobs[job_id].status = "error"
        jobs[job_id].error = str(e)


async def convert_to_wav(file_path: str) -> str:
    """
    Convert audio/video file to WAV 16kHz mono using ffmpeg.
    Uses utils.audio which handles both system and bundled ffmpeg.
    """
    if file_path.endswith(".wav"):
        return file_path

    from utils.audio import convert_to_wav as _convert
    output_path = file_path.rsplit(".", 1)[0] + ".wav"
    return await asyncio.to_thread(_convert, file_path, output_path)


@router.get("/status/{job_id}", response_model=AnalysisStatus)
async def get_job_status(job_id: str):
    """Get the current status of an analysis job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return jobs[job_id]


@router.get("/jobs", response_model=list[str])
async def list_jobs():
    """List all job IDs."""
    return list(jobs.keys())


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a job and its associated files."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    # Clean up files
    for f in UPLOAD_DIR.glob(f"{job_id}*"):
        try:
            os.remove(f)
        except OSError:
            pass

    del jobs[job_id]
    return {"message": f"Job '{job_id}' deleted"}
