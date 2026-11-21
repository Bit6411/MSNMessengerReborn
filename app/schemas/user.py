from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.status import Availability, CurrentStatus


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=24, pattern=r"^[A-Za-z0-9_]+$")
    display_name: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=60)
    bio: str | None = Field(default=None, max_length=280)


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    bio: str
    created_at: datetime
    current_status: CurrentStatus | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class OnlineUser(UserPublic):
    availability: Availability


class OnlineUsersResponse(BaseModel):
    count: int
    users: list[OnlineUser]


class SearchResultItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    bio: str
    is_friend: bool
    matching_status: str


class SearchResponse(BaseModel):
    count: int
    results: list[SearchResultItem]
