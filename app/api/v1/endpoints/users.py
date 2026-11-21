from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.models import Conversation, StatusPost, User
from app.schemas.user import OnlineUsersResponse, SearchResponse, SearchResultItem, UserPublic, UserUpdate
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

    # Split query into individual keywords and build a case-insensitive LIKE filter
    keywords = [kw.strip() for kw in q.split() if kw.strip()]
    if not keywords:
        return SearchResponse(count=0, results=[])

    # Find statuses whose text contains ALL keywords (case-insensitive)
    from sqlalchemy import and_
    conditions = [StatusPost.text.ilike(f"%{kw}%") for kw in keywords]
    matching_statuses = db.scalars(
        select(StatusPost).where(and_(*conditions)).order_by(StatusPost.id.desc())
    ).all()

    if not matching_statuses:
        return SearchResponse(count=0, results=[])

    # Collect unique author IDs (exclude current user)
    author_ids = set()
    author_to_status = {}  # map author_id -> first matching status text
    for status in matching_statuses:
        if status.author_id != current_user.id:
            if status.author_id not in author_ids:
                author_ids.add(status.author_id)
                author_to_status[status.author_id] = status.text

    if not author_ids:
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

    # Fetch user details
    users = db.scalars(
        select(User).where(User.id.in_(author_ids), User.is_active.is_(True))
    ).all()

    # Build results: friends first, then non-friends
    results: list[SearchResultItem] = []
    for user in users:
        is_friend = user.id in friend_ids
        results.append(
            SearchResultItem(
                id=user.id,
                username=user.username,
                display_name=user.display_name,
                bio=user.bio,
                is_friend=is_friend,
                matching_status=author_to_status.get(user.id, ""),
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
