"""Application entrypoint.

Run with:
    uvicorn app.main:app --host 0.0.0.0 --port 47231
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api import router
from app.config import Settings
from app.database import Base, make_engine, make_session_factory
from app import models  # noqa: F401  (register tables on Base.metadata)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    _prepare_storage(settings)
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Base.metadata.create_all(engine)
        yield

    app = FastAPI(
        title="Bulk Certificate Generator",
        summary="Generate certificates for many recipients in one request.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.storage_dir = settings.storage_dir
    app.include_router(router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


def _prepare_storage(settings: Settings) -> None:
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    if settings.database_url.startswith("sqlite:///"):
        raw = settings.database_url.removeprefix("sqlite:///")
        if raw and raw != ":memory:":
            Path(raw).parent.mkdir(parents=True, exist_ok=True)


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
app = create_app()
