import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import Settings, get_settings
from app.database import Database
from app.errors import register_error_handlers
from app.live import LiveHub

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory used by Uvicorn and isolated tests."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.database = Database(settings.sqlalchemy_url)
        try:
            # Re-arm deadline timers lost on restart and close overdue questions.
            await application.state.live_hub.sweep()
        except Exception:
            logger.exception("Startup sweep of open questions failed")
        if settings.live_abandon_after_seconds > 0:
            application.state.live_hub.start_reaper(
                settings.live_abandon_after_seconds,
                settings.live_abandon_check_seconds,
            )
        yield
        await application.state.live_hub.shutdown()
        application.state.database.dispose()

    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.state.live_hub = LiveHub(application)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(application)
    application.include_router(api_router)
    return application


app = create_app()
