from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from sqlalchemy import or_, select

from app.api.deps import CurrentUser, SessionDep
from app.crud.conversation import create_system_message, end_conversation, get_or_create, require_member, to_read
from app.crud.message import create_message, list_messages, to_read as message_to_read
from app.models import Conversation, Message, User
from app.schemas.conversation import ConversationCreate, ConversationRead
from app.schemas.message import MessageCreate, MessagePage, MessageRead
from app.services.chat import publish_new_message

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.post("", response_model=ConversationRead)
def create_conversation(payload: ConversationCreate, db: SessionDep, current_user: CurrentUser):
    conversation = get_or_create(db, current_user.id, payload)
    return to_read(db, conversation, current_user.id)


@router.get("", response_model=list[ConversationRead])
def list_conversations(
    db: SessionDep, current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    records = db.scalars(
        select(Conversation).where(
            or_(Conversation.user_low_id == current_user.id,
                Conversation.user_high_id == current_user.id)
        ).order_by(Conversation.id.desc()).limit(limit).offset(offset)
    ).all()
    return [to_read(db, item, current_user.id) for item in records]


@router.get("/{conversation_id}", response_model=ConversationRead)
def get_conversation(conversation_id: int, db: SessionDep, current_user: CurrentUser):
    item = require_member(db, conversation_id, current_user.id)
    return to_read(db, item, current_user.id)


@router.get("/{conversation_id}/messages", response_model=MessagePage)
def history(
    conversation_id: int, db: SessionDep, current_user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return list_messages(db, conversation_id, current_user.id, limit, offset)


@router.post("/{conversation_id}/messages", response_model=MessageRead,
             status_code=status.HTTP_201_CREATED)
def send_message_http(
    conversation_id: int, payload: MessageCreate, background: BackgroundTasks,
    db: SessionDep, current_user: CurrentUser,
):
    conversation = require_member(db, conversation_id, current_user.id)
    recipients = {conversation.user_low_id, conversation.user_high_id}
    item = create_message(db, conversation_id, current_user.id, payload)
    background.add_task(publish_new_message, recipients, item)
    return item


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def end_conversation_endpoint(
    conversation_id: int, background: BackgroundTasks,
    db: SessionDep, current_user: CurrentUser,
):
    """End a conversation. If both users have ended it, the conversation is deleted.
    Otherwise, a system message notifies the other user."""
    conversation = require_member(db, conversation_id, current_user.id)
    peer_id = (
        conversation.user_high_id if conversation.user_low_id == current_user.id
        else conversation.user_low_id
    )
    peer = db.get(User, peer_id)
    peer_name = peer.display_name if peer else "User"

    # Check if both already ended (conversation may already be deleted)
    if conversation.ended_by == 3:
        raise HTTPException(status_code=400, detail="This conversation has already been ended by both users")

    # Check if this user already ended
    # Bit 1 (value=1) for user_low_id, Bit 2 (value=2) for user_high_id
    bit = 2 if current_user.id == conversation.user_high_id else 1
    if conversation.ended_by & bit:
        raise HTTPException(status_code=400, detail="You already ended this conversation")

    # Set the bit for this user
    conversation.ended_by |= bit

    # Create a system message notifying the other user
    system_msg = create_system_message(
        db,
        conversation_id,
        f"🔔 {current_user.display_name} has ended this conversation.",
    )
    db.flush()

    # If both users have ended, delete the conversation and messages
    if conversation.ended_by == 3:
        db.query(Message).filter(Message.conversation_id == conversation_id).delete(
            synchronize_session='fetch'
        )
        db.delete(conversation)
        db.commit()
    else:
        db.commit()

    # Broadcast the system message to both users
    recipients = {conversation.user_low_id, conversation.user_high_id}
    system_msg_read = message_to_read(system_msg)
    background.add_task(publish_new_message, recipients, system_msg_read)

    # If conversation was deleted, notify about deletion
    if conversation.ended_by == 3:
        background.add_task(
            publish_conversation_deleted,
            recipients,
            conversation_id,
        )


async def publish_conversation_deleted(recipient_ids: set[int], conversation_id: int) -> None:
    """Notify users that a conversation has been deleted."""
    from app.services.presence import presence
    await presence.send_to_users(
        recipient_ids,
        {
            "type": "conversation.deleted",
            "conversation_id": conversation_id,
        },
    )
