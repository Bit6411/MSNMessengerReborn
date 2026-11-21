from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.crud.conversation import require_member
from app.crud.message import create_message
from app.db.session import get_session_factory
from app.schemas.message import MessageCreate, MessageRead
from app.services.presence import presence


def send_using_new_session(
    conversation_id: int, user_id: int, payload: MessageCreate
) -> tuple[set[int], MessageRead]:
    # Used by WebSockets: never hold a SQLAlchemy session for the life of a socket.
    with get_session_factory()() as db:
        conversation = require_member(db, conversation_id, user_id)
        recipient_ids = {conversation.user_low_id, conversation.user_high_id}
        result = create_message(db, conversation_id, user_id, payload)
        return recipient_ids, result


async def publish_new_message(recipient_ids: set[int], message: MessageRead) -> None:
    await presence.send_to_users(
        recipient_ids,
        {"type": "message.new", "message": message.model_dump(mode="json")},
    )
