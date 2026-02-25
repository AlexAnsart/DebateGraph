"""
DebateGraph — PostgreSQL persistence layer.

Tables:
  jobs             — one row per analysis job (status, filename, progress, error)
  graph_snapshots  — one row per completed job (full snapshot + transcription as JSONB)

Uses psycopg2 (sync) — compatible with FastAPI background tasks and asyncio.to_thread.
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional

import psycopg2
import psycopg2.extras
from psycopg2.extensions import connection as PgConnection

logger = logging.getLogger("debategraph.db")

# Set to True only when init_db succeeds. When False, all DB functions return empty/default.
db_available = False

# ─── DDL ────────────────────────────────────────────────────────────────────

_CREATE_JOBS = """
CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    status        TEXT        NOT NULL DEFAULT 'processing',
    created_at    TIMESTAMP   NOT NULL DEFAULT NOW(),
    audio_filename TEXT,
    duration_s    FLOAT,
    progress      FLOAT       NOT NULL DEFAULT 0.0,
    error         TEXT
);
"""

_CREATE_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS graph_snapshots (
    id                TEXT PRIMARY KEY,
    job_id            TEXT        NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    created_at        TIMESTAMP   NOT NULL DEFAULT NOW(),
    snapshot_json     JSONB       NOT NULL,
    transcription_json JSONB,
    num_nodes         INT         NOT NULL DEFAULT 0,
    num_edges         INT         NOT NULL DEFAULT 0,
    num_fallacies     INT         NOT NULL DEFAULT 0,
    num_factchecks    INT         NOT NULL DEFAULT 0,
    speakers          TEXT[]      NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_snapshots_job_id  ON graph_snapshots(job_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_created ON graph_snapshots(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_created      ON jobs(created_at DESC);
"""


# ─── Connection ─────────────────────────────────────────────────────────────

def get_connection() -> PgConnection:
    """Open a new psycopg2 connection from DATABASE_URL."""
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL not set. Add it to your .env file.\n"
            "Example: DATABASE_URL=postgresql://debategraph:debategraph@localhost:5432/debategraph"
        )
    conn = psycopg2.connect(url)
    conn.autocommit = False
    return conn


def init_db() -> bool:
    """Create tables if they don't exist. Called at application startup.
    Returns True on success, False on failure (DB unavailable)."""
    global db_available
    try:
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute(_CREATE_JOBS)
                cur.execute(_CREATE_SNAPSHOTS)
        conn.close()
        db_available = True
        logger.info("PostgreSQL: tables initialized (jobs, graph_snapshots)")
        return True
    except Exception as e:
        logger.error(f"PostgreSQL init failed: {e}")
        db_available = False
        return False


# ─── Job CRUD ────────────────────────────────────────────────────────────────

def create_job(job_id: str, audio_filename: str = None) -> None:
    """Insert a new job row with status='processing'."""
    if not db_available:
        logger.debug("DB unavailable: skipping create_job")
        return
    conn = None
    try:
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO jobs (id, status, audio_filename, progress)
                    VALUES (%s, 'processing', %s, 0.0)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (job_id, audio_filename),
                )
        logger.debug(f"DB: created job {job_id}")
    except psycopg2.OperationalError as e:
        logger.warning(f"DB unavailable: {e}")
    finally:
        if conn:
            conn.close()


def update_job_status(
    job_id: str,
    status: str,
    progress: float = None,
    error: str = None,
    duration_s: float = None,
) -> None:
    """Update job status, progress, error, and/or duration."""
    if not db_available:
        logger.debug("DB unavailable: skipping update_job_status")
        return
    conn = None
    try:
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                fields = ["status = %s"]
                values = [status]
                if progress is not None:
                    fields.append("progress = %s")
                    values.append(progress)
                if error is not None:
                    fields.append("error = %s")
                    values.append(error)
                if duration_s is not None:
                    fields.append("duration_s = %s")
                    values.append(duration_s)
                values.append(job_id)
                cur.execute(
                    f"UPDATE jobs SET {', '.join(fields)} WHERE id = %s",
                    values,
                )
        logger.debug(f"DB: updated job {job_id} → status={status}, progress={progress}")
    except psycopg2.OperationalError as e:
        logger.warning(f"DB unavailable: {e}")
    finally:
        if conn:
            conn.close()


def get_job(job_id: str) -> Optional[dict]:
    """Fetch a single job row as a dict."""
    if not db_available:
        return None
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
            row = cur.fetchone()
            return dict(row) if row else None
    except psycopg2.OperationalError as e:
        logger.warning(f"DB unavailable: {e}")
        return None
    finally:
        if conn:
            conn.close()


def list_jobs() -> list[dict]:
    """
    List all jobs with snapshot metadata (num_nodes, num_edges, speakers).
    Returns newest first.
    """
    if not db_available:
        return []
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    j.id,
                    j.status,
                    j.created_at,
                    j.audio_filename,
                    j.duration_s,
                    j.progress,
                    j.error,
                    s.num_nodes,
                    s.num_edges,
                    s.num_fallacies,
                    s.num_factchecks,
                    s.speakers
                FROM jobs j
                LEFT JOIN graph_snapshots s ON s.job_id = j.id
                ORDER BY j.created_at DESC
                """,
            )
            rows = cur.fetchall()
            result = []
            for row in rows:
                d = dict(row)
                # Serialize datetime for JSON
                if d.get("created_at"):
                    d["created_at"] = d["created_at"].isoformat()
                result.append(d)
            return result
    except psycopg2.OperationalError as e:
        logger.warning(f"DB unavailable: {e}")
        return []
    finally:
        if conn:
            conn.close()


def delete_job(job_id: str) -> bool:
    """Delete a job (cascades to snapshot)."""
    if not db_available:
        return False
    conn = None
    try:
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM jobs WHERE id = %s", (job_id,))
                return cur.rowcount > 0
    except psycopg2.OperationalError as e:
        logger.warning(f"DB unavailable: {e}")
        return False
    finally:
        if conn:
            conn.close()


# ─── Snapshot CRUD ───────────────────────────────────────────────────────────

def save_snapshot(
    job_id: str,
    snapshot: dict,
    transcription: dict = None,
) -> str:
    """
    Persist a graph snapshot to the database.
    Computes metadata (num_nodes, num_edges, etc.) from the snapshot dict.
    Returns the snapshot ID.
    """
    import uuid

    snapshot_id = str(uuid.uuid4())

    # Extract metadata
    nodes = snapshot.get("nodes", [])
    edges = snapshot.get("edges", [])
    num_nodes = len(nodes)
    num_edges = len(edges)
    num_fallacies = sum(len(n.get("fallacies", [])) for n in nodes)
    num_factchecks = sum(
        1 for n in nodes
        if n.get("factcheck_verdict") not in (None, "pending")
    )
    speakers = list(set(n.get("speaker", "") for n in nodes if n.get("speaker")))

    if not db_available:
        logger.debug("DB unavailable: skipping save_snapshot")
        return snapshot_id
    conn = None
    try:
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO graph_snapshots
                        (id, job_id, snapshot_json, transcription_json,
                         num_nodes, num_edges, num_fallacies, num_factchecks, speakers)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        snapshot_id,
                        job_id,
                        json.dumps(snapshot),
                        json.dumps(transcription) if transcription else None,
                        num_nodes,
                        num_edges,
                        num_fallacies,
                        num_factchecks,
                        speakers,
                    ),
                )
        logger.info(
            f"DB: saved snapshot {snapshot_id} for job {job_id} "
            f"({num_nodes} nodes, {num_edges} edges, {num_fallacies} fallacies)"
        )
        return snapshot_id
    except psycopg2.OperationalError as e:
        logger.warning(f"DB unavailable: {e}")
        return snapshot_id
    finally:
        if conn:
            conn.close()


def get_snapshot(job_id: str) -> Optional[dict]:
    """
    Load the graph snapshot for a given job_id.
    Returns dict with 'snapshot_json' and 'transcription_json' keys.
    """
    if not db_available:
        return None
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT s.*, j.audio_filename, j.created_at as job_created_at
                FROM graph_snapshots s
                JOIN jobs j ON j.id = s.job_id
                WHERE s.job_id = %s
                ORDER BY s.created_at DESC
                LIMIT 1
                """,
                (job_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get("created_at"):
                d["created_at"] = d["created_at"].isoformat()
            if d.get("job_created_at"):
                d["job_created_at"] = d["job_created_at"].isoformat()
            return d
    except psycopg2.OperationalError as e:
        logger.warning(f"DB unavailable: {e}")
        return None
    finally:
        if conn:
            conn.close()


def get_all_snapshots_meta() -> list[dict]:
    """
    Return metadata for all snapshots (for the DB viewer).
    """
    if not db_available:
        return []
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    s.id as snapshot_id,
                    s.job_id,
                    s.created_at,
                    s.num_nodes,
                    s.num_edges,
                    s.num_fallacies,
                    s.num_factchecks,
                    s.speakers,
                    j.audio_filename,
                    j.status as job_status
                FROM graph_snapshots s
                JOIN jobs j ON j.id = s.job_id
                ORDER BY s.created_at DESC
                """,
            )
            rows = cur.fetchall()
            result = []
            for row in rows:
                d = dict(row)
                if d.get("created_at"):
                    d["created_at"] = d["created_at"].isoformat()
                result.append(d)
            return result
    except psycopg2.OperationalError as e:
        logger.warning(f"DB unavailable: {e}")
        return []
    finally:
        if conn:
            conn.close()
