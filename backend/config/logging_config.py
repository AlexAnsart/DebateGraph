"""
DebateGraph — Structured Logging Configuration
Creates organized log files per session in the logs/ directory.

Structure:
  logs/
    session_<YYYYmmdd_HHMMSS_ffffff>/
      meta.json              — Session start/end times
      pipeline.txt            — Main pipeline flow
      transcription.txt      — STT + diarization details
      ontological.txt        — Claim extraction details
      skeptic.txt            — Fallacy detection details
      researcher.txt         — Fact-checking details
      errors.txt             — All errors across agents
      llm_calls.jsonl        — Every LLM call (input/output, timestamps)
      nodes.jsonl            — Every node (claim) created
      edges.jsonl            — Every edge (relation) created
      fallacies.jsonl        — Every fallacy annotation
      factchecks.jsonl       — Every fact-check result
      transcription_chunks.jsonl — STT chunk outputs
"""

import os
import logging
from datetime import datetime
from pathlib import Path
from config.settings import LOG_DIR


def setup_session_logging(session_id: str = None) -> str:
    """
    Set up structured logging for a new analysis session.
    Folder name is always a timestamp (YYYYmmdd_HHMMSS) for easy ordering.

    Args:
        session_id: Optional; ignored for folder name (kept for API compatibility).

    Returns:
        Path to the session log directory.
    """
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S") + "_" + str(now.microsecond).zfill(6)
    session_dir = os.path.join(LOG_DIR, f"session_{timestamp}")
    Path(session_dir).mkdir(parents=True, exist_ok=True)
    
    # Define log files for each component
    log_files = {
        "debategraph": "pipeline.txt",
        "debategraph.streaming": "streaming.txt",
        "debategraph.transcription": "transcription.txt",
        "debategraph.ontological": "ontological.txt",
        "debategraph.skeptic": "skeptic.txt",
        "debategraph.researcher": "researcher.txt",
    }
    
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    for logger_name, filename in log_files.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)
        
        # File handler for this component
        fh = logging.FileHandler(
            os.path.join(session_dir, filename),
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    
    # Error log — captures ERROR+ from all loggers
    error_handler = logging.FileHandler(
        os.path.join(session_dir, "errors.txt"),
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logging.getLogger("debategraph").addHandler(error_handler)
    
    # Also log to console
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    
    root_logger = logging.getLogger("debategraph")
    # Avoid duplicate console handlers
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) 
               for h in root_logger.handlers):
        root_logger.addHandler(console)
    
    logging.getLogger("debategraph").info(f"Session logging initialized: {session_dir}")
    
    return session_dir


def get_session_logger(component: str) -> logging.Logger:
    """
    Get a logger for a specific pipeline component.
    
    Args:
        component: One of 'transcription', 'ontological', 'skeptic', 'researcher'
    
    Returns:
        Logger instance
    """
    return logging.getLogger(f"debategraph.{component}")
