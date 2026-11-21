from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.models import User
from app.schemas.user import OnlineUsersResponse, UserPublic, UserUpdate
from app.services.presence import presence

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=list[UserPublic])
def list_users(
    db: SessionDep, current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return db.scalars(
        select(User).where(User.is_active.is_(True), User.id != current_user.id)
        .order_by(User.username).offset(offset).limit(limit)
    ).all()


@router.get("/online", response_model=OnlineUsersResponse)
async def online_users(db: SessionDep, current_user: CurrentUser):
    ids = await presence.online_user_ids()
    users = db.scalars(select(User).where(User.id.in_(ids)).order_by(User.username)).all() if ids else []
    return OnlineUsersResponse(count=len(users), users=users)


@router.patch("/me", response_model=UserPublic)
def update_me(payload: UserUpdate, db: SessionDep, current_user: CurrentUser):
    changes = payload.model_dump(exclude_unset=True)
    if any(v is None for v in changes.values()):
        raise HTTPException(status_code=422, detail="Fields cannot be null")
    if "display_name" in changes and not changes["display_name"].strip():
        raise HTTPException(status_code=422, detail="Display name cannot be blank")
    for key, value in changes.items():
        setattr(current_user, key, value.strip() if key == "display_name" else value)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/{user_id}", response_model=UserPublic)
def user_profile(user_id: int, db: SessionDep, current_user: CurrentUser):
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="User not found")
    return user
