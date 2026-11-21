from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StatusCreate(BaseModel):
    text: str = Field(min_length=1, max_length=280)


class StatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    author_id: int
    text: str
    created_at: datetime
