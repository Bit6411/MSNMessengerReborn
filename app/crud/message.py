from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.crud.conversation import require_member
from app.models import Attachment, Message
from app.schemas.message import AttachmentRead, MessageCreate, MessagePage, MessageRead


def to_read(message: Message) -> MessageRead:
    return MessageRead(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        text=message.text,
        created_at=message.created_at,
        attachments=[
            AttachmentRead(
                id=a.id,
                original_name=a.original_name,
                content_type=a.content_type,
                size_bytes=a.size_bytes,
                url=f"/api/v1/media/{a.id}",
            )
            for a in message.attachments
        ],
    )


def create_message(
    db: Session, conversation_id: int, sender_id: int, payload: MessageCreate
) -> MessageRead:
    require_member(db, conversation_id, sender_id)
    attachments = []
    if payload.attachment_ids:
        attachments = list(
            db.scalars(
                select(Attachment)
                .where(Attachment.id.in_(payload.attachment_ids))
                .with_for_update()
            )
        )
        if len(attachments) != len(payload.attachment_ids):
            raise HTTPException(status_code=400, detail="Invalid attachment ID")
        for attachment in attachments:
            if (
                attachment.uploader_id != sender_id
                or attachment.conversation_id != conversation_id
                or attachment.message_id is not None
            ):
                raise HTTPException(status_code=400, detail="Attachment cannot be used")
    message = Message(
        conversation_id=conversation_id,
        sender_id=sender_id,
        text=payload.text,
    )
    db.add(message)
    db.flush()
    for attachment in attachments:
        attachment.message_id = message.id
    db.commit()
    # Re-query with all media loaded, returning a plain Pydantic object.
    fresh = db.scalar(
        select(Message).options(selectinload(Message.attachments)).where(Message.id == message.id)
    )
    return to_read(fresh)


def list_messages(
    db: Session, conversation_id: int, user_id: int, limit: int, offset: int
) -> MessagePage:
    require_member(db, conversation_id, user_id)
    total = db.scalar(
        select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
    ) or 0
    messages = db.scalars(
        select(Message)
        .options(selectinload(Message.attachments))
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    next_offset = offset + len(messages)
    has_more = next_offset < total
    return MessagePage(
        items=[to_read(m) for m in messages],
        limit=limit,
        offset=offset,
        total=total,
        has_more=has_more,
        next_offset=next_offset if has_more else None,
    )
