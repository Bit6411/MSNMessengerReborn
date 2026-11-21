from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import read_token_user_id
from app.db.session import get_session_factory
from app.models import User

_bearer = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    with get_session_factory()() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user_id = read_token_user_id(credentials.credentials)
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
