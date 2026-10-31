"""FastAPI application factory."""
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.error_handlers import register_exception_handlers
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import dashboard, evidence, executions, health, runs, tasks, versions
from app.llm.client import make_featherless_client
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
            "Tasks, executions with a validated lifecycle, a deterministic evaluator, an evaluator-led "
            "acceptance gate with typed evidence, local evidence bundles, and an orchestrator that drives "
            "the Featherless Generator and Critic. No LLM scores or approves anything. No ZK, IPFS or "
            "blockchain integration yet."
        ),
        lifespan=lifespan,
    )
    app.state.settings = settings
    # Identifies this server process. A run claimed under a different id belongs to an earlier process
    # (the server restarted): it is reported as `stalled` and never resumed automatically.
    app.state.instance_id = uuid.uuid4().hex
    # How a run obtains its LLM client. Tests replace this with a scripted fake (no network).
    app.state.llm_client_factory = make_featherless_client
    # Browser access is restricted to an explicit allowlist. No wildcard; credentials stay off, so a
    # malicious page cannot ride a user's cookies (the API uses none today).
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type"],
        )
    register_exception_handlers(app)
    for router in (health.router, tasks.router, executions.router, runs.router, versions.router,
                   evidence.router, dashboard.router):
        app.include_router(router, prefix="/api")
    return app


app = create_app()
