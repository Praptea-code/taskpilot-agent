from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from agent import __version__
from agent.api.goals import router as goals_router
from agent.config import get_settings
from agent.core.clock import SystemClock
from agent.core.monitor import Monitor, MonitorConfig
from agent.db.session import get_sessionmaker


def create_app() -> FastAPI:
    settings = get_settings()
    monitor = Monitor(
        get_sessionmaker(settings.database_url),
        SystemClock(),
        MonitorConfig(grace_minutes=settings.grace_minutes),
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

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
