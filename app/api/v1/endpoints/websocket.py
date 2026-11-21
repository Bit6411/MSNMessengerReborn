from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.security import read_token_user_id
from app.db.session import get_session_factory
from app.models import User
from app.schemas.message import MessageCreate
from app.services.chat import publish_new_message, send_using_new_session
from app.services.presence import presence

router = APIRouter(tags=["WebSocket"])


def _is_active_user(user_id: int) -> bool:
    with get_session_factory()() as db:
        user = db.get(User, user_id)
        return bool(user and user.is_active)


@router.websocket("/ws")
async def chat_socket(websocket: WebSocket):
    # Browsers cannot set an Authorization header in WebSocket(). For this local
    # MVP, the short-lived JWT travels in the URL. Use WSS and stronger session
    # transport for a public deployment; avoid logging WebSocket URLs/tokens.
    origin = websocket.headers.get("origin")
    http_scheme = "https" if websocket.url.scheme == "wss" else "http"
    same_origin = f"{http_scheme}://{websocket.url.netloc}"
    if origin and origin != same_origin and origin not in get_settings().cors_origin_list:
        await websocket.close(code=1008)
        return
    token = websocket.query_params.get("token", "")
    try:
        user_id = read_token_user_id(token)
        if not await run_in_threadpool(_is_active_user, user_id):
            raise HTTPException(status_code=401)
    except HTTPException:
        await websocket.close(code=1008)
        return

    was_offline = await presence.connect(user_id, websocket)
    if was_offline:
        await presence.publish_presence()
    else:
        await websocket.send_json({"type": "presence.update",
                                   "count": len(await presence.online_user_ids()),
                                   "user_ids": await presence.online_user_ids()})
    try:
        while True:
            data = await websocket.receive_json()
            if not isinstance(data, dict) or data.get("type") != "message.send":
                await websocket.send_json({"type": "message.error", "detail": "Unknown event"})
                continue
            try:
                conv_id = data.get("conversation_id")
                if type(conv_id) is not int or conv_id <= 0:
                    raise ValueError("Invalid conversation ID")
                payload = MessageCreate.model_validate({
                    "text": data.get("text", ""),
                    "attachment_ids": data.get("attachment_ids", []),
                })
                recipients, item = await run_in_threadpool(
                    send_using_new_session, conv_id, user_id, payload
                )
                await publish_new_message(recipients, item)
            except (ValidationError, HTTPException, ValueError) as exc:
                detail = getattr(exc, "detail", "Invalid message or attachment")
                await websocket.send_json({"type": "message.error", "detail": str(detail)})
    except WebSocketDisconnect:
        pass
    finally:
        if await presence.disconnect(user_id, websocket):
            await presence.publish_presence()
