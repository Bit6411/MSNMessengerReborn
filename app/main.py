from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.v1.router import api_router
from app.core.config import PROJECT_ROOT, get_settings
from app.db.init_db import init_db

STATIC_DIR = PROJECT_ROOT / "static"
TEMPLATES_DIR = PROJECT_ROOT / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Good for an MVP: create missing tables. This does NOT migrate changed models.
    init_db()
    get_settings().upload_path.mkdir(parents=True, exist_ok=True)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.state.templates = templates
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/", include_in_schema=False)
    def homepage(request: Request):
        return templates.TemplateResponse(request, "index.html", {"app_name": settings.app_name})

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
