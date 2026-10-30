"""FastAPI application factory."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.error_handlers import register_exception_handlers
from app.api.routes import executions, health, tasks, versions
from app.config import Settings, get_settings
from app.database import create_db_engine, init_db, make_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_db_engine(settings.database_url)
        init_db(engine)  # idempotent create-if-missing
        app.state.engine = engine
        app.state.session_factory = make_session_factory(engine)
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(
        title="AutoEvolve Protocol API",
        version=__version__,
        description=(
            "Backend foundation: tasks, executions with a validated lifecycle, versions, "
            "evaluations and Critic feedback storage. No AI, ZK, IPFS or blockchain integration yet."
        ),
        lifespan=lifespan,
    )
    app.state.settings = settings
    register_exception_handlers(app)
    for router in (health.router, tasks.router, executions.router, versions.router):
        app.include_router(router, prefix="/api")
    return app


app = create_app()
