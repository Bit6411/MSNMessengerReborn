from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.status import StatusRead
from app.schemas.user import UserPublic


class ConversationCreate(BaseModel):
    recipient_id: int = Field(ge=1)
    status_id: int | None = Field(default=None, ge=1)


class ConversationRead(BaseModel):
    id: int
    other_user: UserPublic
    status: StatusRead | None
    created_at: datetime
    ended_by_me: bool = False
