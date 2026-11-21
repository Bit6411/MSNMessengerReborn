from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, SessionDep
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas.user import LoginRequest, RegisterRequest, TokenResponse, UserPublic

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: SessionDep):
    username = payload.username.lower()
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(status_code=409, detail="Username already taken")
    user = User(
        username=username,
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password),
    )
    if not user.display_name:
        raise HTTPException(status_code=422, detail="Display name cannot be blank")
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username already taken") from exc
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: SessionDep):
    user = db.scalar(select(User).where(User.username == payload.username.lower()))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    return TokenResponse(access_token=create_access_token(user.id), user=user)


@router.get("/me", response_model=UserPublic)
def me(current_user: CurrentUser):
    return current_user
