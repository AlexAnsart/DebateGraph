"""
DebateGraph — FastAPI Backend Entrypoint
Real-Time Argumentative Analysis Engine

Provides:
- REST API for file upload and analysis status
- WebSocket endpoints for real-time updates
- Static file serving for the frontend build
- Demo mode endpoint for testing without audio files
"""

import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("debategraph")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    logger.info("=" * 60)
    logger.info("  DebateGraph — Argumentative Analysis Engine")
    logger.info("=" * 60)
    from config.settings import LLM_MODEL, WHISPER_MODEL, WHISPER_DEVICE
    logger.info(f"  LLM_MODEL:      {LLM_MODEL}")
    logger.info(f"  WHISPER_MODEL:  {WHISPER_MODEL}")
    logger.info(f"  WHISPER_DEVICE: {WHISPER_DEVICE}")
    logger.info(f"  ANTHROPIC_API:  {'configured' if os.getenv('ANTHROPIC_API_KEY') else 'not set (demo mode)'}")
    logger.info(f"  TAVILY_API:     {'configured' if os.getenv('TAVILY_API_KEY') else 'not set (mock fact-check)'}")
    logger.info("=" * 60)

    # Ensure upload directory exists
    Path("uploads").mkdir(parents=True, exist_ok=True)

    yield

    logger.info("DebateGraph shutting down")


# Create FastAPI app
app = FastAPI(
    title="DebateGraph",
    description="Real-Time Argumentative Analysis Engine — From Speech to Structured Logic",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS configuration
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
from api.routes.upload import router as upload_router
from api.routes.ws import router as ws_router

app.include_router(upload_router)
app.include_router(ws_router)


# ─── Demo Endpoint ──────────────────────────────────────────

@app.post("/api/demo")
async def run_demo():
    """
    Run the analysis pipeline on demo data (no file upload needed).
    Useful for testing the frontend without WhisperX or audio files.
    """
    from pipeline.transcription import _transcribe_demo
    from agents.orchestrator import run_analysis_pipeline
    from graph.store import DebateGraphStore

    logger.info("Running demo analysis...")

    transcription = _transcribe_demo("demo")
    graph_store = DebateGraphStore()
    snapshot = await run_analysis_pipeline(transcription, graph_store)

    return JSONResponse(content={
        "status": "complete",
        "transcription": transcription.model_dump(mode="json"),
        "graph": snapshot.model_dump(mode="json"),
    })


# ─── Snapshot Endpoint ──────────────────────────────────────

@app.get("/api/snapshot/latest")
async def get_latest_snapshot():
    """
    Return the latest pre-computed analysis snapshot (if available).
    Looks for logs/e2e_test_snapshot.json first, then any session snapshot.
    Useful for loading results without re-running the pipeline.
    """
    import json

    # Check for e2e test snapshot
    snapshot_paths = [
        Path("..") / "logs" / "e2e_test_snapshot.json",
        Path("logs") / "e2e_test_snapshot.json",
    ]

    for snapshot_path in snapshot_paths:
        if snapshot_path.exists():
            try:
                with open(snapshot_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return JSONResponse(content={
                    "status": "complete",
                    "graph": data,
                    "source": str(snapshot_path),
                })
            except Exception as e:
                logger.error(f"Failed to load snapshot from {snapshot_path}: {e}")

    return JSONResponse(
        status_code=404,
        content={"status": "not_found", "message": "No pre-computed snapshot available. Upload a file or run the demo."},
    )


# ─── Health Check ────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "0.2.0",
        "whisper_available": _check_whisper(),
        "anthropic_configured": bool(os.getenv("ANTHROPIC_API_KEY")),
        "tavily_configured": bool(os.getenv("TAVILY_API_KEY")),
    }


def _check_whisper() -> bool:
    try:
        import whisperx
        return True
    except ImportError:
        return False


# ─── Serve Frontend Static Files (production) ───────────────

frontend_dist = Path("frontend/dist")
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
    logger.info(f"Serving frontend from {frontend_dist}")


# ─── Run with uvicorn ────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("BACKEND_HOST", "0.0.0.0")
    port = int(os.getenv("BACKEND_PORT", "8000"))

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info",
    )
