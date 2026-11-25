import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agent import __version__
from agent.api.actions import router as actions_router
from agent.api.checkins import router as checkins_router
from agent.api.credentials import router as credentials_router
from agent.api.goals import router as goals_router
from agent.api.inbound import router as inbound_router
from agent.api.notifications import router as notifications_router
from agent.api.sessions import router as sessions_router
from agent.api.users import router as users_router
from agent.api.voice import router as voice_router
from agent.config import get_settings
from agent.core.clock import SystemClock
from agent.core.logging import bind_log_context, configure_logging, reset_log_context
from agent.core.monitor import Monitor, MonitorConfig
from agent.core.rate_limit import RateLimiter
from agent.db.session import get_sessionmaker
from agent.executors.registry import build_default_registry

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    maker = get_sessionmaker(settings.database_url)
    monitor = Monitor(
        maker,
        SystemClock(),
        MonitorConfig(
            grace_minutes=settings.grace_minutes,
            lock_minutes=settings.monitor_lock_minutes,
        ),
        build_default_registry(maker),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await monitor.start(settings.database_url)
        try:
            yield
        finally:
            monitor.stop()

    app = FastAPI(title="taskpilot-agent", version=settings.version, lifespan=lifespan)
    limiter = RateLimiter(settings.rate_limit_per_minute)

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        if settings.rate_limit_per_minute > 0:
            key = request.client.host if request.client else "unknown"
            if not limiter.allow(key):
                return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
        return await call_next(request)

    @app.middleware("http")
    async def log_context(request: Request, call_next):
        values: dict[str, object] = {}
        raw_user_id = request.headers.get("x-user-id")
        if raw_user_id is not None:
            values["user_id"] = raw_user_id
        parts = request.url.path.split("/")
        if "goals" in parts:
            index = parts.index("goals")
            if index + 1 < len(parts) and parts[index + 1].isdigit():
                values["goal_id"] = parts[index + 1]
        token = bind_log_context(**values)
        try:
            return await call_next(request)
        finally:
            reset_log_context(token)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.monitor = monitor

    app.include_router(users_router)
    app.include_router(credentials_router)
    app.include_router(goals_router)
    app.include_router(inbound_router)
    app.include_router(checkins_router)
    app.include_router(actions_router)
    app.include_router(notifications_router)
    app.include_router(sessions_router)
    app.include_router(voice_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, error: Exception) -> JSONResponse:
        logger.exception(
            "unhandled_error",
            exc_info=error,
            extra={"path": request.url.path},
        )
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app


app = create_app()
