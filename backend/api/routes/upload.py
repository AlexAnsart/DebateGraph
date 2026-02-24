"""
Upload endpoint for audio/video files.
Handles file reception, conversion to WAV, and triggers the analysis pipeline.
All jobs and snapshots are persisted to PostgreSQL.
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
    GraphSnapshot,
    TranscriptionResult,
)
from pipeline.transcription import transcribe_audio
from agents.orchestrator import run_analysis_pipeline
from graph.store import DebateGraphStore
from db.database import (
    create_job,
    update_job_status,
    get_job,
    list_jobs as db_list_jobs,
    delete_job as db_delete_job,
    save_snapshot,
    get_snapshot,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["upload"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".mp3", ".wav", ".mp4", ".webm", ".ogg", ".flac", ".m4a", ".avi", ".mkv"}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB


# ─── Upload ──────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """
    Upload an audio or video file for analysis.
    The file is saved, and the analysis pipeline is launched as a background task.
    Job state is persisted to PostgreSQL.
    """
    ext = Path(file.filename or "unknown.wav").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

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

    # Persist job to DB
    create_job(job_id, audio_filename=file.filename)

    # Launch analysis pipeline in background
    background_tasks.add_task(process_file, job_id, str(file_path), file.filename)

    return UploadResponse(
        job_id=job_id,
        status="processing",
        message=f"File '{file.filename}' uploaded successfully. Analysis started.",
    )


async def process_file(job_id: str, file_path: str, original_filename: str = None):
    """
    Background task: runs the full analysis pipeline on an uploaded file.
    Updates job status in PostgreSQL at each stage.
    """
    try:
        # Stage 1: Transcription
        update_job_status(job_id, "transcribing", progress=0.1)
        logger.info(f"[{job_id}] Starting transcription of {original_filename}...")

        wav_path = await convert_to_wav(file_path)

        update_job_status(job_id, "transcribing", progress=0.2)
        transcription = await asyncio.to_thread(transcribe_audio, wav_path)
        update_job_status(job_id, "transcribing", progress=0.5)
        logger.info(f"[{job_id}] Transcription complete: {len(transcription.segments)} segments")

        # Stage 2: Analysis pipeline
        update_job_status(job_id, "extracting", progress=0.6)

        graph_store = DebateGraphStore()
        graph_snapshot = await run_analysis_pipeline(
            transcription, graph_store, session_id=job_id
        )

        # Persist snapshot to DB
        snapshot_dict = graph_snapshot.model_dump(mode="json")
        transcription_dict = transcription.model_dump(mode="json")
        save_snapshot(job_id, snapshot_dict, transcription_dict)

        update_job_status(job_id, "complete", progress=1.0)
        logger.info(f"[{job_id}] Analysis complete — persisted to DB")

    except Exception as e:
        logger.error(f"[{job_id}] Pipeline error: {e}", exc_info=True)
        update_job_status(job_id, "error", error=str(e))


async def convert_to_wav(file_path: str) -> str:
    """Convert audio/video file to WAV 16kHz mono using ffmpeg."""
    if file_path.endswith(".wav"):
        return file_path
    from utils.audio import convert_to_wav as _convert
    output_path = file_path.rsplit(".", 1)[0] + ".wav"
    return await asyncio.to_thread(_convert, file_path, output_path)


# ─── Status ──────────────────────────────────────────────────

@router.get("/status/{job_id}")
async def get_job_status(job_id: str):
    """
    Get the current status of an analysis job.
    If complete, also returns the graph snapshot and transcription from DB.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    response = {
        "job_id": job["id"],
        "status": job["status"],
        "progress": job["progress"],
        "error": job.get("error"),
        "graph": None,
        "transcription": None,
    }

    # If complete, load snapshot from DB
    if job["status"] == "complete":
        snap = get_snapshot(job_id)
        if snap:
            response["graph"] = snap["snapshot_json"]
            response["transcription"] = snap.get("transcription_json")

    return JSONResponse(content=response)


# ─── Jobs list ───────────────────────────────────────────────

@router.get("/jobs")
async def list_jobs():
    """
    List all jobs with metadata (filename, status, node/edge counts, speakers).
    Returns newest first.
    """
    return db_list_jobs()


# ─── Latest snapshot ─────────────────────────────────────────

@router.get("/snapshot/latest")
async def load_latest_snapshot():
    """
    Return the most recent completed analysis snapshot from the database.
    """
    import json as _json
    jobs = db_list_jobs()
    completed = [j for j in jobs if j.get("status") == "complete"]
    if not completed:
        raise HTTPException(status_code=404, detail="No completed jobs found")
    
    latest_job = completed[0]  # already sorted newest first
    snap = get_snapshot(latest_job["id"])
    if not snap:
        raise HTTPException(status_code=404, detail="No snapshot found for latest job")
    
    return JSONResponse(content={
        "status": "complete",
        "job_id": latest_job["id"],
        "audio_filename": latest_job.get("audio_filename"),
        "created_at": latest_job.get("created_at"),
        "graph": snap["snapshot_json"],
        "transcription": snap.get("transcription_json"),
        "meta": {
            "num_nodes": snap["num_nodes"],
            "num_edges": snap["num_edges"],
            "num_fallacies": snap["num_fallacies"],
            "num_factchecks": snap["num_factchecks"],
            "speakers": snap["speakers"],
        },
    })


# ─── Load snapshot ───────────────────────────────────────────

@router.get("/snapshot/{job_id}")
async def load_snapshot(job_id: str):
    """
    Load a previously-computed graph snapshot from the database.
    Returns the full graph + transcription without re-running the pipeline.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    if job["status"] != "complete":
        raise HTTPException(
            status_code=400,
            detail=f"Job '{job_id}' is not complete (status: {job['status']})",
        )

    snap = get_snapshot(job_id)
    if not snap:
        raise HTTPException(
            status_code=404,
            detail=f"No snapshot found for job '{job_id}'",
        )

    return JSONResponse(content={
        "status": "complete",
        "job_id": job_id,
        "audio_filename": job.get("audio_filename"),
        "created_at": snap.get("job_created_at"),
        "graph": snap["snapshot_json"],
        "transcription": snap.get("transcription_json"),
        "meta": {
            "num_nodes": snap["num_nodes"],
            "num_edges": snap["num_edges"],
            "num_fallacies": snap["num_fallacies"],
            "num_factchecks": snap["num_factchecks"],
            "speakers": snap["speakers"],
        },
    })


# ─── Delete job ──────────────────────────────────────────────

@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a job and its associated files and DB records."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    # Clean up uploaded files
    for f in UPLOAD_DIR.glob(f"{job_id}*"):
        try:
            os.remove(f)
        except OSError:
            pass

    db_delete_job(job_id)
    return {"message": f"Job '{job_id}' deleted"}
