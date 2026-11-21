from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversation_pair", "user_low_id", "user_high_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_low_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    user_high_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # Uniquely identifies a normal DM or a DM spawned from a particular status.
    # A non-null scope key ensures ordinary DMs and status-linked threads are unique.
    scope_key: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    status_id: Mapped[int | None] = mapped_column(ForeignKey("statuses.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    # Bitmask tracking which users have requested to end this conversation.
    # Bit 0 -> user_low_id ended, Bit 1 -> user_high_id ended.
    # When both bits are set (value == 3), the conversation is deleted.
    ended_by: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
