"""
app/main.py
────────────
FastAPI application entry point.
Configures CORS, structured logging, and mounts all routes.
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.api.routes import router

settings = get_settings()

# ── Structured logging setup ──────────────────────────────────────────────────
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(__import__("logging"), settings.log_level)
    ),
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="ParcelPilot Support Agent",
    description="Internal AI support agent for ParcelPilot operations.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

origins = settings.backend_cors_origins
if not origins or "*" in origins:
    allow_origins = ["*"]
    allow_credentials = False
else:
    allow_origins = origins
    allow_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.on_event("startup")
async def startup_event():
    log = structlog.get_logger()
    log.info("app.startup", env=settings.app_env, snapshot_time="2026-08-16T11:00:00+05:30")
