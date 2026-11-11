from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from commerce_api.api.routes import auth, catalog, commerce, health, inventory, onboarding, tenants, warehouses
from commerce_api.core.config import Settings
from commerce_api.db.session import create_engine, create_session_factory
from commerce_api.services.errors import CommerceError


def create_app(settings: Settings, session_factory: Any | None = None) -> FastAPI:
    owns_engine = session_factory is None
    engine = create_engine(settings.database_url) if owns_engine else None
    factory = session_factory or create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        if owns_engine:
            await engine.dispose()

    app = FastAPI(title="Cube Tech Commerce API", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = factory
    app.include_router(health.router)
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(onboarding.router, prefix="/api/v1")
    app.include_router(tenants.router, prefix="/api/v1")
    app.include_router(catalog.router, prefix="/api/v1/catalog")
    app.include_router(warehouses.router, prefix="/api/v1")
    app.include_router(inventory.router, prefix="/api/v1")
    app.include_router(commerce.router, prefix="/api/v1")

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(_request, _exc):
        return JSONResponse(status_code=409, content={"detail": "A resource with that value already exists"})

    @app.exception_handler(CommerceError)
    async def commerce_error_handler(_request, exc: CommerceError):
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    return app