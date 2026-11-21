from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.models import StatusPost, User
from app.schemas.status import StatusCreate, StatusRead

router = APIRouter(tags=["Statuses"])


@router.post("/statuses", response_model=StatusRead, status_code=status.HTTP_201_CREATED)
def post_status(payload: StatusCreate, db: SessionDep, current_user: CurrentUser):
    if not payload.text.strip():
        raise HTTPException(status_code=422, detail="Status cannot be blank")
    item = StatusPost(author_id=current_user.id, text=payload.text.strip())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/statuses", response_model=list[StatusRead])
def feed(db: SessionDep, current_user: CurrentUser,
         limit: int = Query(default=30, ge=1, le=100),
         offset: int = Query(default=0, ge=0)):
    return db.scalars(select(StatusPost).order_by(StatusPost.id.desc()).limit(limit).offset(offset)).all()


@router.get("/statuses/{status_id}", response_model=StatusRead)
def get_status(status_id: int, db: SessionDep, current_user: CurrentUser):
    item = db.get(StatusPost, status_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Status not found")
    return item


@router.get("/users/{user_id}/statuses", response_model=list[StatusRead])
def user_statuses(
    user_id: int, db: SessionDep, current_user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db.scalars(
        select(StatusPost).where(StatusPost.author_id == user_id)
        .order_by(StatusPost.id.desc()).limit(limit).offset(offset)
    ).all()
