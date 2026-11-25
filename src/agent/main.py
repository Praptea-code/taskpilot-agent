from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from agent import __version__
from agent.api.actions import router as actions_router
from agent.api.checkins import router as checkins_router
from agent.api.goals import router as goals_router
from agent.config import get_settings
from agent.core.clock import SystemClock
from agent.core.monitor import Monitor, MonitorConfig
from agent.db.session import get_sessionmaker
from agent.executors.registry import build_default_registry


def create_app() -> FastAPI:
    settings = get_settings()
    maker = get_sessionmaker(settings.database_url)
    monitor = Monitor(
        maker,
        SystemClock(),
        MonitorConfig(grace_minutes=settings.grace_minutes),
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
    app.state.monitor = monitor
    app.include_router(goals_router)
    app.include_router(checkins_router)
    app.include_router(actions_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
