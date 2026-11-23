"""FastAPI application factory.

    uvicorn backend.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import backend.accounting.guards  # noqa: F401  (registers immutability guards)
from backend.audit.service import request_context
from backend.config import get_settings
from backend.core.exceptions import DomainError
from backend.database import models  # noqa: F401
from backend.database.session import SessionLocal, get_engine

log = logging.getLogger("ucfin")

API_ROUTERS = [
    "backend.api.routers_auth",
    "backend.api.routers_admin",
    "backend.api.routers_masters",
    "backend.api.routers_journals",
    "backend.api.routers_reports",
    "backend.api.routers_ap",
    "backend.api.routers_ar",
    "backend.api.routers_banking",
    "backend.api.routers_tax",
    "backend.api.routers_assets",
    "backend.api.routers_budget",
    "backend.api.routers_cinema",
    "backend.api.routers_closing",
    "backend.api.routers_imports",
]


def create_app() -> FastAPI:
    s = get_settings()
    docs = s.enable_api_docs
    app = FastAPI(title=s.app_name, version="1.0.0",
                  description="Accounting & finance system for Universal Cinemas / NC Entertainment",
                  docs_url="/api/docs" if docs else None, redoc_url="/api/redoc" if docs else None,
                  openapi_url="/api/openapi.json" if docs else None)

    if s.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in s.cors_origins.split(",")],
                           allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def context_and_headers(request: Request, call_next):
        fwd = request.headers.get("x-forwarded-for")
        ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else None)
        token = request_context.set({"ip": ip, "ua": request.headers.get("user-agent")})
        try:
            response = await call_next(request)
        finally:
            request_context.reset(token)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if s.environment == "production":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        elif not request.url.path.startswith(("/api/docs", "/api/redoc")):
            response.headers.setdefault("Content-Security-Policy",
                                        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                                        "img-src 'self' data: blob:; connect-src 'self'; font-src 'self' data:; "
                                        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
        return response

    @app.exception_handler(DomainError)
    async def domain_error(_request: Request, exc: DomainError):
        return JSONResponse(status_code=exc.status_code,
                            content={"error": exc.code, "message": exc.message, "details": exc.details})

    @app.exception_handler(IntegrityError)
    async def integrity_error(_request: Request, exc: IntegrityError):
        log.warning("integrity error: %s", exc.orig)
        return JSONResponse(status_code=409, content={"error": "integrity_error",
                                                      "message": "The change conflicts with existing data "
                                                                 "(duplicate or protected record)",
                                                      "details": str(exc.orig).split("\n")[0][:300]})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        details = [f"{'.'.join(str(x) for x in e['loc'][1:])}: {e['msg']}" for e in exc.errors()]
        return JSONResponse(status_code=422, content={"error": "invalid_request", "message": "Invalid input",
                                                      "details": details})

    import importlib
    for mod_name in API_ROUTERS:
        try:
            mod = importlib.import_module(mod_name)
        except ModuleNotFoundError as exc:
            if exc.name == mod_name:
                continue  # module not built yet
            raise
        for attr in ("router", "files_router", "export_router"):
            r = getattr(mod, attr, None)
            if r is not None:
                app.include_router(r)

    @app.get("/api/health", tags=["system"])
    def health():
        get_engine()
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ok", "app": s.app_name, "environment": s.environment}

    dist = Path(s.frontend_dist)
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            if full_path.startswith("api/"):
                return JSONResponse(status_code=404, content={"error": "not_found", "message": "Unknown API route"})
            candidate = (dist / full_path).resolve()
            if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
