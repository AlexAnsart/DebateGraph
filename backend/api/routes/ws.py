"""
WebSocket handler for real-time streaming mode (Phase 3).
Currently provides a status streaming endpoint for monitoring analysis progress.
"""

import json
import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manages active WebSocket connections."""

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
            self.active_connections[job_id].remove(websocket)
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]
        logger.info(f"WebSocket disconnected for job {job_id}")

    async def broadcast(self, job_id: str, message: dict):
        """Send a message to all connections watching a specific job."""
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


@router.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint for streaming analysis updates.
    Clients connect with a job_id and receive real-time progress updates.
    """
    await manager.connect(websocket, job_id)

    try:
        # Import here to avoid circular imports
        from api.routes.upload import jobs

        while True:
            # Check for client messages (e.g., settings changes)
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

            # Send current job status
            if job_id in jobs:
                status = jobs[job_id]
                await websocket.send_json({
                    "type": "status",
                    "data": status.model_dump(mode="json"),
                })

                # If job is complete or errored, send final update and close
                if status.status in ("complete", "error"):
                    await websocket.send_json({
                        "type": "done",
                        "data": status.model_dump(mode="json"),
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


@router.websocket("/ws/stream")
async def stream_microphone(websocket: WebSocket):
    """
    WebSocket endpoint for real-time microphone streaming (Phase 3).
    Receives audio chunks from the frontend and returns transcription + analysis.
    Currently a placeholder that echoes connection status.
    """
    await websocket.accept()
    logger.info("Microphone stream WebSocket connected")

    try:
        await websocket.send_json({
            "type": "info",
            "data": {
                "message": "Real-time streaming is planned for Phase 3. "
                           "Please use file upload mode for now."
            },
        })

        while True:
            # Receive audio chunks (binary data)
            data = await websocket.receive_bytes()
            logger.debug(f"Received audio chunk: {len(data)} bytes")

            # Phase 3: Process chunk through faster-whisper streaming
            # For now, acknowledge receipt
            await websocket.send_json({
                "type": "ack",
                "data": {"bytes_received": len(data)},
            })

    except WebSocketDisconnect:
        logger.info("Microphone stream disconnected")
    except Exception as e:
        logger.error(f"Microphone stream error: {e}")
