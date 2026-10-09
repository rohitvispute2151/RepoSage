"""FastAPI main application entry point for RepoSage service.

Exposes REST APIs under /v1 prefix, Prometheus metrics, and ops health checks.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
import time
from typing import Callable
import uuid

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from reposage.api.routes_repos import router as repos_router
from reposage.api.routes_tasks import router as tasks_router
from reposage.db.session import engine, get_db, init_db
from reposage.observability.logging import current_request_id, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown hooks."""
    setup_logging()
    # Initialize DB tables and extensions
    try:
        await init_db()
    except Exception:
        pass
    yield


app = FastAPI(
    title="RepoSage API",
    description="Agentic Codebase Assistant with verifiable citations and sandbox-proven repairs.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for local frontend/tools
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_and_timing_middleware(
    request: Request, call_next: Callable
) -> Response:
    """Inject X-Request-Id header and bind correlation context."""
    req_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
    current_request_id.set(req_id)
    start_time = time.perf_counter()

    response: Response = await call_next(request)

    duration_ms = (time.perf_counter() - start_time) * 1000.0
    response.headers["X-Request-Id"] = req_id
    response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"
    return response


# Mount versioned API routes under /v1
app.include_router(repos_router, prefix="/v1")
app.include_router(tasks_router, prefix="/v1")


@app.get("/healthz", tags=["ops"])
async def health_check() -> dict[str, str]:
    """Liveness probe confirming API service responsiveness."""
    return {"status": "ok"}


@app.get("/readyz", tags=["ops"])
async def readiness_check(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """Readiness probe verifying database connectivity."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}


@app.get("/metrics", tags=["ops"])
async def metrics_endpoint() -> Response:
    """Prometheus metrics scrape target."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
