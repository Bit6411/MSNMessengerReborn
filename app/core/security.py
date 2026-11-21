from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException, status

from app.core.config import get_settings

_password_hasher = PasswordHasher()
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    return jwt.encode(
        {"sub": str(user_id), "exp": expires},
        settings.jwt_secret_key.get_secret_value(),
        algorithm=_ALGORITHM,
    )


def read_token_user_id(token: str) -> int:
    try:
        data = jwt.decode(
            token,
            get_settings().jwt_secret_key.get_secret_value(),
            algorithms=[_ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
        user_id = int(data["sub"])
        if user_id <= 0:
            raise ValueError("Invalid ID")
        return user_id
    except (jwt.InvalidTokenError, TypeError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
