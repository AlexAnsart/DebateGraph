"""
WebSocket handlers:
  /ws/{job_id}   — polls job status from PostgreSQL (file upload mode)
  /ws/stream     — live audio/video stream with incremental graph updates
"""

import json
import uuid
import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


# ─── Connection Manager ───────────────────────────────────────────────────────

class ConnectionManager:
    """Manages active WebSocket connections per job."""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, job_id: str):
        await websocket.accept()
        if job_id not in self.active_connections:
            self.active_connections[job_id] = []
        self.active_connections[job_id].append(websocket)
        logger.info(f"WebSocket connected for job {job_id}")

    def disconnect(self, websocket: WebSocket, job_id: str):
        if job_id in self.active_connections:
            try:
                self.active_connections[job_id].remove(websocket)
            except ValueError:
                pass
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]
        logger.info(f"WebSocket disconnected for job {job_id}")

    async def broadcast(self, job_id: str, message: dict):
        if job_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[job_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    disconnected.append(connection)
            for conn in disconnected:
                self.disconnect(conn, job_id)


manager = ConnectionManager()


# ─── Job Status WebSocket ─────────────────────────────────────────────────────

@router.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint for monitoring file-upload analysis jobs.
    Polls PostgreSQL every 0.5s and broadcasts status updates.
    """
    await manager.connect(websocket, job_id)

    try:
        from db.database import get_job

        while True:
            # Check for client messages
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(), timeout=1.0
                )
                message = json.loads(data)
                logger.debug(f"Received from client: {message}")
            except asyncio.TimeoutError:
                pass
            except json.JSONDecodeError:
                pass

            # Poll job status from DB
            job = await asyncio.to_thread(get_job, job_id)
            if job:
                await websocket.send_json({
                    "type": "status",
                    "data": {
                        "job_id": job["id"],
                        "status": job["status"],
                        "progress": job["progress"],
                        "error": job.get("error"),
                    },
                })

                if job["status"] in ("complete", "error"):
                    await websocket.send_json({
                        "type": "done",
                        "data": {
                            "job_id": job["id"],
                            "status": job["status"],
                            "progress": job["progress"],
                        },
                    })
                    break
            else:
                await websocket.send_json({
                    "type": "error",
                    "data": {"message": f"Job '{job_id}' not found"},
                })
                break

            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        logger.info(f"Client disconnected from job {job_id}")
    except Exception as e:
        logger.error(f"WebSocket error for job {job_id}: {e}")
    finally:
        manager.disconnect(websocket, job_id)


# ─── Live Streaming WebSocket ─────────────────────────────────────────────────

@router.websocket("/ws/stream")
async def stream_live(websocket: WebSocket):
    """
    Live streaming WebSocket endpoint.

    Protocol (client → server):
      Binary frames: raw audio chunks (WebM/Opus from MediaRecorder, or MP3/WAV)
      JSON text frames:
        {"type": "start", "session_id": "...", "enable_factcheck": true}
        {"type": "stop"}
        {"type": "ping"}

    Protocol (server → client):
      {"type": "stream_started", "session_id": "..."}
      {"type": "chunk_received", "chunk_index": N, "size_bytes": N, "time_offset": N}
      {"type": "transcription_update", "chunk_index": N, "new_segments": [...], "total_segments": N}
      {"type": "graph_update", "chunk_index": N, "graph": {...}, "transcription": {...}, "stats": {...}}
      {"type": "finalizing", "message": "..."}
      {"type": "stream_complete", "session_id": "...", "graph": {...}, "transcription": {...}}
      {"type": "error", "stage": "...", "message": "..."}
      {"type": "pong"}
    """
    await websocket.accept()
    session_id = str(uuid.uuid4())[:8]
    logger.info(f"[{session_id}] Live stream WebSocket connected")

    pipeline = None
    chunk_index = 0
    time_offset = 0.0
    chunk_duration = 15.0  # seconds per chunk (estimated)
    audio_format = "webm"

    try:
        from pipeline.streaming_pipeline import LiveStreamingPipeline

        async def send_update(message: dict):
            """Callback to send updates to the frontend."""
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"[{session_id}] Failed to send update: {e}")

        # Wait for start message or first audio chunk
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive(), timeout=30.0)
            except asyncio.TimeoutError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Timeout waiting for stream start"
                })
                return

            # Handle text control messages
            if "text" in msg:
                try:
                    data = json.loads(msg["text"])
                    msg_type = data.get("type", "")

                    if msg_type == "start":
                        session_id = data.get("session_id", session_id)
                        enable_factcheck = data.get("enable_factcheck", True)
                        enable_llm_fallacy = data.get("enable_llm_fallacy", True)
                        audio_format = data.get("audio_format", "webm")
                        chunk_duration = float(data.get("chunk_duration", 15.0))

                        pipeline = LiveStreamingPipeline(
                            on_update=send_update,
                            session_id=session_id,
                            enable_factcheck=enable_factcheck,
                            enable_llm_fallacy=enable_llm_fallacy,
                        )
                        await pipeline.start()
                        logger.info(f"[{session_id}] Stream started (format={audio_format})")
                        continue

                    elif msg_type == "stop":
                        logger.info(f"[{session_id}] Stop signal received")
                        break

                    elif msg_type == "ping":
                        await websocket.send_json({"type": "pong"})
                        continue

                except json.JSONDecodeError:
                    pass

            # Handle binary audio data
            elif "bytes" in msg and msg["bytes"]:
                audio_bytes = msg["bytes"]

                if not audio_bytes or len(audio_bytes) < 100:
                    logger.debug(f"[{session_id}] Skipping tiny chunk ({len(audio_bytes)} bytes)")
                    continue

                # Auto-start pipeline if not started yet
                if pipeline is None:
                    pipeline = LiveStreamingPipeline(
                        on_update=send_update,
                        session_id=session_id,
                        enable_factcheck=True,
                        enable_llm_fallacy=True,
                    )
                    await pipeline.start()

                # Process the audio chunk
                filename = f"chunk_{chunk_index}.{audio_format}"
                await pipeline.process_chunk(
                    audio_bytes=audio_bytes,
                    chunk_index=chunk_index,
                    time_offset=time_offset,
                    filename=filename,
                )

                chunk_index += 1
                time_offset += chunk_duration

                # Check for stop signal (non-blocking)
                try:
                    ctrl = await asyncio.wait_for(websocket.receive(), timeout=0.01)
                    if "text" in ctrl:
                        data = json.loads(ctrl["text"])
                        if data.get("type") == "stop":
                            break
                except (asyncio.TimeoutError, json.JSONDecodeError):
                    pass

        # Finalize
        if pipeline:
            snapshot = await pipeline.finalize()

            # Persist to DB
            try:
                await _persist_stream_to_db(session_id, pipeline, snapshot)
            except Exception as e:
                logger.error(f"[{session_id}] DB persistence failed: {e}")

    except WebSocketDisconnect:
        logger.info(f"[{session_id}] Client disconnected")
        if pipeline:
            try:
                await pipeline.finalize()
            except Exception:
                pass
    except Exception as e:
        logger.error(f"[{session_id}] Stream error: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "stage": "pipeline",
                "message": str(e),
            })
        except Exception:
            pass


async def _persist_stream_to_db(
    session_id: str,
    pipeline,
    snapshot,
) -> str:
    """Persist a live stream session to PostgreSQL."""
    try:
        from db.database import create_job, update_job_status, save_snapshot

        job_id = f"live_{session_id}"
        create_job(job_id, audio_filename=f"live_stream_{session_id}")

        snapshot_dict = snapshot.model_dump(mode="json")
        transcription_dict = {
            "segments": [s.model_dump() for s in pipeline.all_segments],
            "language": "en",
            "num_speakers": len(set(s.speaker for s in pipeline.all_segments)),
        }

        save_snapshot(job_id, snapshot_dict, transcription_dict)
        update_job_status(job_id, "complete", progress=1.0)

        logger.info(f"[{session_id}] Persisted to DB as job {job_id}")
        return job_id
    except Exception as e:
        logger.error(f"[{session_id}] DB persistence error: {e}")
        raise
