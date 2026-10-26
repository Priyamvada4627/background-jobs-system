from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.api.ws_manager import ws_manager

router = APIRouter(tags=["WebSockets"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Real-time WebSocket connection streaming system and job state transition events.
    Enables zero-refresh live updates for dashboards.
    """
    await ws_manager.connect(websocket)
    try:
        # Greet newly connected client
        await websocket.send_json({
            "event": "connected",
            "data": {
                "message": "Connected to real-time Background Job System stream.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        })
        while True:
            # Keep connection alive; accept any heartbeat pings from client
            client_msg = await websocket.receive_text()
            if client_msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
