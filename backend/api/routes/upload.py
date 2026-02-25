"""
Upload endpoint for audio/video files.
Handles file reception, conversion to WAV, and triggers the analysis pipeline.
All jobs and snapshots are persisted to PostgreSQL.
Uses chunk-based streaming with aiofiles for reliable video/audio uploads.
"""

import os
import uuid
import asyncio
import logging
from pathlib import Path

import aiofiles
import mimetypes

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse

from config.settings import UPLOAD_DIR as UPLOAD_DIR_CFG, DEMOS_DIR
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

UPLOAD_DIR = Path(UPLOAD_DIR_CFG).resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DEMOS_PATH = Path(DEMOS_DIR).resolve()

ALLOWED_EXTENSIONS = {".mp3", ".wav", ".mp4", ".webm", ".ogg", ".flac", ".m4a", ".avi", ".mkv"}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB


def _resolve_media_path(job_id: str) -> Path | None:
    """
    Resolve media file path: first check UPLOAD_DIR, then fall back to DEMOS_DIR
    using job's source_path or audio_filename (for run_pipeline_test / demo jobs).
    """
    matches = list(UPLOAD_DIR.glob(f"{job_id}.*"))
    originals = [m for m in matches if m.suffix != ".wav"] or matches
    if originals:
        return originals[0]

    job = get_job(job_id)
    if not job:
        return None
    source_path = job.get("source_path") or job.get("audio_filename")
    if not source_path:
        return None
    # source_path may be "demos/obama_romney_10min.mp3" or "obama_romney_10min.mp3"
    demo_filename = Path(source_path).name
    demo_path = DEMOS_PATH / demo_filename
    if demo_path.exists() and demo_path.suffix.lower() in {".mp3", ".mp4", ".webm", ".ogg", ".m4a", ".avi", ".mkv"}:
        return demo_path
    return None


def _has_media_file(job_id: str) -> bool:
    """Check if media file exists (uploads or demos fallback)."""
    return _resolve_media_path(job_id) is not None


def _get_media_url(job_id: str) -> str | None:
    """Return the media URL for a job if the file exists."""
    if _has_media_file(job_id):
        return f"/api/media/{job_id}"
    return None


# ─── Media serving ───────────────────────────────────────────

@router.get("/media/{job_id}")
async def serve_media(job_id: str):
    """Serve the media file for video/audio playback (uploads or demos fallback)."""
    file_path = _resolve_media_path(job_id)
    if not file_path:
        raise HTTPException(status_code=404, detail=f"Media file for job '{job_id}' not found")

    media_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=file_path.name,
    )


# ─── Upload ──────────────────────────────────────────────────

CHUNK_SIZE = 1024 * 1024  # 1 MB chunks for streaming


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """
    Upload an audio or video file for analysis.
    Uses chunk-based streaming to avoid memory issues and ensure complete writes.
    Supports both audio (WAV, MP3, etc.) and video (MP4, WebM, etc.).
    """
    ext = Path(file.filename or "unknown.wav").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    job_id = str(uuid.uuid4())
    final_path = UPLOAD_DIR / f"{job_id}{ext}"

    try:
        total_bytes = 0
        async with aiofiles.open(final_path, "wb") as f:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                if total_bytes + len(chunk) > MAX_FILE_SIZE:
                    await file.close()
                    final_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="File too large (max 500 MB)")
                await f.write(chunk)
                total_bytes += len(chunk)

        await file.close()

        if total_bytes == 0:
            final_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Empty file")

        # Verify write completed
        final_size = final_path.stat().st_size
        if final_size != total_bytes:
            final_path.unlink(missing_ok=True)
            raise RuntimeError(f"Write incomplete: {final_size} != {total_bytes}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}")
        final_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Failed to save file")

    create_job(job_id, audio_filename=file.filename)

    # Delay before ffmpeg (Windows Defender can briefly lock new files)
    background_tasks.add_task(process_file, job_id, str(final_path), file.filename)

    return UploadResponse(
        job_id=job_id,
        status="processing",
        message=f"File '{file.filename}' uploaded successfully. Analysis started.",
    )


async def process_file(
    job_id: str,
    file_path: str,
    original_filename: str = None,
):
    """
    Background task: runs the full analysis pipeline on an uploaded file.
    File is in UPLOAD_DIR. Extracts audio from video, transcribes, builds graph.
    """
    path = Path(file_path).resolve()
    try:
        # Brief delay so Windows Defender/antivirus releases file handle
        await asyncio.sleep(1)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if path.stat().st_size == 0:
            raise FileNotFoundError(f"File is empty: {file_path}")

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

        # Clean up temp WAV (original stays in UPLOAD_DIR for media serving)
        wav_p = Path(wav_path)
        if wav_p.exists():
            wav_p.unlink()

        update_job_status(job_id, "complete", progress=1.0)
        logger.info(f"[{job_id}] Analysis complete — persisted to DB")

    except Exception as e:
        logger.error(f"[{job_id}] Pipeline error: {e}", exc_info=True)
        update_job_status(job_id, "error", error=str(e))
        # Clean up temp WAV
        wav_p = Path(file_path).with_suffix(".wav")
        if wav_p.exists():
            try:
                wav_p.unlink()
            except OSError:
                pass
        # Clean up uploaded file on error
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass


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
        "media_url": None,
    }

    # If complete, load snapshot from DB
    if job["status"] == "complete":
        snap = get_snapshot(job_id)
        if snap:
            response["graph"] = snap["snapshot_json"]
            response["transcription"] = snap.get("transcription_json")
        response["media_url"] = _get_media_url(job_id)

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
        "media_url": _get_media_url(latest_job["id"]),
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
        "media_url": _get_media_url(job_id),
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
