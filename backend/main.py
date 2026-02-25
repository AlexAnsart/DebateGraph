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

# Load environment variables (override=True to replace empty system env vars)
load_dotenv(override=True)

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
    logger.info(f"  DATABASE_URL:   {'configured' if os.getenv('DATABASE_URL') else 'not set (no persistence)'}")
    logger.info("=" * 60)

    # Ensure upload directory exists
    Path("uploads").mkdir(parents=True, exist_ok=True)

    # Initialize PostgreSQL tables
    if os.getenv("DATABASE_URL"):
        try:
            from db.database import init_db
            init_db()
            logger.info("PostgreSQL: ready")
        except Exception as e:
            logger.error(f"PostgreSQL init failed: {e}")
            logger.warning("Continuing without database persistence")
    else:
        logger.warning("DATABASE_URL not set — jobs will not be persisted")

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
from api.routes.dbviewer import router as dbviewer_router

app.include_router(upload_router)
app.include_router(ws_router)
app.include_router(dbviewer_router)


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
    port = int(os.getenv("BACKEND_PORT", "8010"))

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info",
    )
