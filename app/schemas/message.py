from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class MessageCreate(BaseModel):
    text: str = Field(default="", max_length=4000)
    attachment_ids: list[int] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def must_have_content(self) -> "MessageCreate":
        if not self.text.strip() and not self.attachment_ids:
            raise ValueError("A message needs text and/or an attachment")
        if len(set(self.attachment_ids)) != len(self.attachment_ids):
            raise ValueError("Duplicate attachment IDs")
        if any(attachment_id <= 0 for attachment_id in self.attachment_ids):
            raise ValueError("Invalid attachment ID")
        return self


class AttachmentRead(BaseModel):
    id: int
    original_name: str
    content_type: str
    size_bytes: int
    url: str


class MessageRead(BaseModel):
    id: int
    conversation_id: int
    sender_id: int
    text: str
    attachments: list[AttachmentRead]
    created_at: datetime


class MessagePage(BaseModel):
    # Newest-first. offset=0 is the newest page.
    items: list[MessageRead]
    limit: int
    offset: int
    total: int
    has_more: bool
    next_offset: int | None
