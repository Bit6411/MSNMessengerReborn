from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Conversation, Message, StatusPost, User
from app.schemas.conversation import ConversationCreate, ConversationRead


def require_member(db: Session, conversation_id: int, user_id: int) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if user_id not in (conversation.user_low_id, conversation.user_high_id):
        raise HTTPException(status_code=403, detail="Not a participant in this conversation")
    return conversation


def to_read(db: Session, conversation: Conversation, user_id: int) -> ConversationRead:
    peer_id = (
        conversation.user_high_id if conversation.user_low_id == user_id
        else conversation.user_low_id
    )
    return ConversationRead(
        id=conversation.id,
        other_user=db.get(User, peer_id),
        status=db.get(StatusPost, conversation.status_id) if conversation.status_id else None,
        created_at=conversation.created_at,
    )


def get_or_create(db: Session, user_id: int, data: ConversationCreate) -> Conversation:
    if data.recipient_id == user_id:
        raise HTTPException(status_code=400, detail="Cannot message yourself")
    recipient = db.get(User, data.recipient_id)
    if recipient is None or not recipient.is_active:
        raise HTTPException(status_code=404, detail="Recipient not found")
    if data.status_id is not None:
        status = db.get(StatusPost, data.status_id)
        if status is None:
            raise HTTPException(status_code=404, detail="Status not found")
        if status.author_id != data.recipient_id:
            raise HTTPException(status_code=400, detail="Can only reply to recipient's status")
    low, high = sorted((user_id, data.recipient_id))
    scope_key = (
        f"status:{data.status_id}:{low}:{high}" if data.status_id
        else f"dm:{low}:{high}"
    )
    existing = db.scalar(select(Conversation).where(Conversation.scope_key == scope_key))
    if existing:
        return existing
    result = Conversation(
        user_low_id=low, user_high_id=high, scope_key=scope_key, status_id=data.status_id
    )
    db.add(result)
    try:
        db.commit()
    except IntegrityError:
        # Another request may have created the same unique-scoped conversation.
        db.rollback()
        existing = db.scalar(select(Conversation).where(Conversation.scope_key == scope_key))
        if existing:
            return existing
        raise
    db.refresh(result)
    return result


def end_conversation(db: Session, conversation_id: int, user_id: int) -> None:
    """Mark a user as having ended the conversation. If both users have ended,
    delete the conversation and all its messages."""
    conversation = require_member(db, conversation_id, user_id)
    # Bit 1 (value=1) for user_low_id, Bit 2 (value=2) for user_high_id
    bit = 2 if user_id == conversation.user_high_id else 1
    
    # Check if this user already ended
    if conversation.ended_by & bit:
        raise HTTPException(status_code=400, detail="You already ended this conversation")
    
    # Set the bit for this user
    conversation.ended_by |= bit
    
    # If both users have ended (bitmask == 3), delete the conversation
    if conversation.ended_by == 3:
        db.query(Message).filter(Message.conversation_id == conversation_id).delete(
            synchronize_session='fetch'
        )
        db.delete(conversation)
        db.commit()
    else:
        db.commit()


def create_system_message(db: Session, conversation_id: int, text: str) -> Message:
    """Create a system message (sender_id = None) to notify participants."""
    message = Message(
        conversation_id=conversation_id,
        sender_id=None,  # System message marker
        text=text,
    )
    db.add(message)
    db.flush()
    return message
