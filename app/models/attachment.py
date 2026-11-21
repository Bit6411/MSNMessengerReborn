from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    uploader_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), index=True, nullable=True)
    stored_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    message: Mapped["Message | None"] = relationship(  # noqa: F821
        back_populates="attachments"
    )
