import logging
from typing import Set, Dict, Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages active WebSocket connections and broadcasts real-time system events."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.debug(f"WebSocket client connected. Total active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.discard(websocket)
        logger.debug(f"WebSocket client disconnected. Total active: {len(self.active_connections)}")

    async def broadcast(self, event_type: str, data: Dict[str, Any]) -> None:
        """Broadcasts a JSON-serialized event to all connected clients."""
        if not self.active_connections:
            return

        message = {
            "event": event_type,
            "data": data,
        }

        stale_connections = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as exc:
                logger.debug(f"Error sending to WebSocket connection: {exc}")
                stale_connections.add(connection)

        for connection in stale_connections:
            self.active_connections.discard(connection)


ws_manager = WebSocketManager()
