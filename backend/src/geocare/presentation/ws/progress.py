"""WebSocket progress tracking for job status updates."""

import asyncio
import json
from typing import Dict, Set
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query, status
from fastapi.websockets import WebSocketState

from geocare.config.container import container
from geocare.presentation.api.deps import get_current_user
from geocare.domain.entities.user import User

router = APIRouter()


class ConnectionManager:
    """Manage WebSocket connections for job progress."""

    def __init__(self):
        # job_id -> set of WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.user_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, job_id: str, user_id: str):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()

        if job_id not in self.active_connections:
            self.active_connections[job_id] = set()
        self.active_connections[job_id].add(websocket)

        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        self.user_connections[user_id].add(websocket)

    def disconnect(self, websocket: WebSocket, job_id: str, user_id: str):
        """Remove a WebSocket connection."""
        if job_id in self.active_connections:
            self.active_connections[job_id].discard(websocket)
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]

        if user_id in self.user_connections:
            self.user_connections[user_id].discard(websocket)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]

    async def send_progress(self, job_id: str, data: dict):
        """Send progress update to all connections for a job."""
        if job_id not in self.active_connections:
            return

        message = json.dumps({
            "type": "progress",
            "job_id": job_id,
            **data,
        })

        disconnected = set()
        for ws in self.active_connections[job_id]:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(message)
                else:
                    disconnected.add(ws)
            except Exception:
                disconnected.add(ws)

        # Clean up disconnected
        for ws in disconnected:
            self.active_connections[job_id].discard(ws)

    async def send_status(self, job_id: str, status: str, error: str = None):
        """Send status change notification."""
        await self.send_progress(job_id, {
            "type": "status",
            "status": status,
            "error": error,
        })

    async def broadcast_to_user(self, user_id: str, message: dict):
        """Send message to all connections for a user."""
        if user_id not in self.user_connections:
            return

        text = json.dumps(message)
        disconnected = set()
        for ws in self.user_connections[user_id]:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(text)
                else:
                    disconnected.add(ws)
            except Exception:
                disconnected.add(ws)

        for ws in disconnected:
            self.user_connections[user_id].discard(ws)


# Global connection manager
manager = ConnectionManager()


@router.websocket("/progress/{job_id}")
async def websocket_progress(
    websocket: WebSocket,
    job_id: UUID,
    token: str = Query(...),
    current_user: User = Depends(get_current_user),
):
    """
    WebSocket endpoint for real-time job progress updates.

    Connect with: ws://host/api/v1/ws/progress/{job_id}?token={access_token}

    Messages received:
    - {"type": "ping"} -> responds with {"type": "pong"}

    Messages sent:
    - {"type": "progress", "job_id": "...", "processed": 100, "total": 1000, "pct": 10.0, "rate": 50.0, "eta": 18}
    - {"type": "status", "job_id": "...", "status": "completed", "error": null}
    - {"type": "batch_complete", "job_id": "...", "batch": 5, "succeeded": 48000, "failed": 2000}
    """
    # Verify user owns the job
    job_repo = container.infrastructure.repositories.job_repository
    job = await job_repo.get(job_id)
    if not job:
        await websocket.close(code=status.WS_1008, reason="Job not found")
        return

    if job.user_id != current_user.id and current_user.role != "admin":
        await websocket.close(code=status.WS_1008, reason="Not authorized")
        return

    # Connect
    await manager.connect(websocket, str(job_id), str(current_user.id))

    try:
        # Send initial status
        await websocket.send_text(json.dumps({
            "type": "connected",
            "job_id": str(job_id),
            "status": job.status.value,
            "progress_pct": job.progress_pct,
        }))

        # Listen for messages (ping/pong)
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                message = json.loads(data)
                if message.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_text(json.dumps({"type": "keepalive"}))
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger = get_logger("geocare.ws")
        logger.error("WebSocket error", job_id=str(job_id), error=str(e))
    finally:
        manager.disconnect(websocket, str(job_id), str(current_user.id))


# Function for workers to send progress updates
async def publish_job_progress(job_id: str, data: dict):
    """Publish progress update to WebSocket connections."""
    await manager.send_progress(job_id, data)


async def publish_job_status(job_id: str, status: str, error: str = None):
    """Publish status change to WebSocket connections."""
    await manager.send_status(job_id, status, error)