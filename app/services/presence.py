import asyncio
from collections import defaultdict

from fastapi import WebSocket, WebSocketDisconnect


class PresenceManager:
    """In-memory demo manager. Use Redis/pub-sub for a multi-worker deployment."""

    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, user_id: int, websocket: WebSocket) -> bool:
        await websocket.accept()
        async with self._lock:
            first_connection = not self._connections[user_id]
            self._connections[user_id].add(websocket)
            return first_connection

    async def disconnect(self, user_id: int, websocket: WebSocket) -> bool:
        async with self._lock:
            sockets = self._connections.get(user_id)
            if sockets is None:
                return False
            sockets.discard(websocket)
            if not sockets:
                del self._connections[user_id]
                return True
            return False

    async def online_user_ids(self) -> list[int]:
        async with self._lock:
            return sorted(self._connections.keys())

    async def send_to_users(self, user_ids: set[int], message: dict) -> None:
        async with self._lock:
            sockets = [
                websocket
                for user_id in user_ids
                for websocket in self._connections.get(user_id, ())
            ]
        for websocket in sockets:
            try:
                await websocket.send_json(message)
            except (OSError, RuntimeError, WebSocketDisconnect):
                # The owning receive loop will remove a disconnected socket.
                pass

    async def publish_presence(self) -> None:
        user_ids = await self.online_user_ids()
        await self.send_to_users(
            set(user_ids),
            {"type": "presence.update", "count": len(user_ids), "user_ids": user_ids},
        )


presence = PresenceManager()
