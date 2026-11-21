from fastapi import APIRouter

from app.api.v1.endpoints import auth, conversations, media, statuses, users, websocket

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(statuses.router)
api_router.include_router(conversations.router)
api_router.include_router(media.router)
api_router.include_router(websocket.router)
