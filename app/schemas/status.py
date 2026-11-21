from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Availability = Literal["online", "idle", "dnd"]


class CurrentStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    availability: Availability = "online"
    description: str = Field(default="", max_length=280)


class StatusCreate(BaseModel):
    text: str = Field(min_length=1, max_length=280)


class StatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    author_id: int
    text: str
    created_at: datetime
