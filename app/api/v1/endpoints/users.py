from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, SessionDep
from app.models import Conversation, StatusPost, User, UserStatus
from app.schemas.status import CurrentStatus, StatusRead
from app.schemas.user import OnlineUser, OnlineUsersResponse, SearchResponse, SearchResultItem, UserPublic, UserUpdate
from app.services.presence import presence

router = APIRouter(prefix="/users", tags=["Users"])


def _to_user_public(db, user):
    """Convert a User ORM object to UserPublic, including the latest status post."""
    # Fetch the latest status post for this user
    latest = db.scalar(
        select(StatusPost)
        .where(StatusPost.author_id == user.id)
        .order_by(StatusPost.id.desc())
        .limit(1)
    )
    status_read = None
    if latest:
        status_read = StatusRead(
            id=latest.id,
            author_id=latest.author_id,
            text=latest.text,
            created_at=latest.created_at,
        )
    current_status = None
    if user.current_status:
        current_status = CurrentStatus(
            availability=user.current_status.availability,
            description=user.current_status.description,
        )
    return UserPublic(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        bio=user.bio,
        created_at=user.created_at,
        current_status=current_status,
        latest_status_post=status_read,
    )


@router.get("", response_model=list[UserPublic])
def list_users(
    db: SessionDep, current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    users = db.scalars(
        select(User).where(User.is_active.is_(True), User.id != current_user.id)
        .order_by(User.username).offset(offset).limit(limit)
    ).all()
    return [_to_user_public(db, u) for u in users]


@router.get("/online", response_model=OnlineUsersResponse)
async def online_users(db: SessionDep, current_user: CurrentUser):
    ids = await presence.online_user_ids()
    online = db.scalars(select(User).where(User.id.in_(ids)).order_by(User.username)) if ids else []
    users = [
        OnlineUser(
            **_to_user_public(db, user).model_dump(),
            availability=user.current_status.availability if user.current_status else "online",
        )
        for user in online
    ]
    return OnlineUsersResponse(count=len(users), users=users)


@router.get("/me/status", response_model=CurrentStatus)
def get_my_status(db: SessionDep, current_user: CurrentUser):
    return db.get(UserStatus, current_user.id) or CurrentStatus()


@router.put("/me/status", response_model=CurrentStatus)
def set_my_status(
    payload: CurrentStatus, db: SessionDep, current_user: CurrentUser, background_tasks: BackgroundTasks,
):
    values = payload.model_dump()
    db.execute(
        insert(UserStatus).values(user_id=current_user.id, **values)
        .on_conflict_do_update(index_elements=[UserStatus.user_id], set_=values)
    )
    db.commit()
    background_tasks.add_task(presence.publish_presence)
    return payload


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


@router.get("/search", response_model=SearchResponse)
def search_users(
    q: str = Query(min_length=1, description="Search keywords"),
    db: SessionDep = None,
    current_user: CurrentUser = None,
):
    """Search users by status keywords. Friends (users with existing conversations)
    are returned first, followed by non-friends."""
    if not q.strip():
        return SearchResponse(count=0, results=[])

    matches = db.execute(
        select(User, UserStatus.description)
        .join(UserStatus, UserStatus.user_id == User.id)
        .where(
            User.is_active.is_(True),
            User.id != current_user.id,
            UserStatus.description != "",
            *(UserStatus.description.icontains(keyword, autoescape=True) for keyword in q.split()),
        )
    ).all()
    if not matches:
        return SearchResponse(count=0, results=[])

    # Determine which authors are "friends" (have an existing conversation)
    friend_ids = set()
    for conv in db.scalars(
        select(Conversation).where(
            (Conversation.user_low_id == current_user.id) | (Conversation.user_high_id == current_user.id)
        )
    ).all():
        peer = (
            conv.user_high_id if conv.user_low_id == current_user.id
            else conv.user_low_id
        )
        friend_ids.add(peer)

    # Build results: friends first, then non-friends
    results: list[SearchResultItem] = []
    for user, description in matches:
        is_friend = user.id in friend_ids
        results.append(
            SearchResultItem(
                id=user.id,
                username=user.username,
                display_name=user.display_name,
                bio=user.bio,
                is_friend=is_friend,
                matching_status=description,
            )
        )

    # Sort: friends first, then by username
    results.sort(key=lambda r: (not r.is_friend, r.username))

    return SearchResponse(count=len(results), results=results)


@router.get("/{user_id}", response_model=UserPublic)
def user_profile(user_id: int, db: SessionDep, current_user: CurrentUser):
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="User not found")
    return user
