"""
Bamboo Flute Practice Platform - FastAPI Main Entry Point.

This module initializes the FastAPI application and configures
all middleware, routes, and static file serving.
"""

import time
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.database import engine, Base
from app.api.endpoints import auth, scores, playlists, recordings, debug, admin
from app.core.middleware import SecurityMiddleware
from app.core.exceptions import AppException, ERROR_CODES
from app.core.responses import APIErrorResponse
from app.core.logging_config import log_request
from app.models import statistics  # Register statistics models

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Bamboo Flute Practice Platform")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        t0 = time.time()
        response = await call_next(request)
        duration = (time.time() - t0) * 1000
        log_request(request.method, request.url.path, response.status_code, duration)
        return response


app.add_middleware(RequestLoggingMiddleware)

# Security Middleware (Inner layer, wrapped by CORS)
app.add_middleware(SecurityMiddleware)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files directory
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# ── Global Exception Handlers ──

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=_http_status_for_code(exc.code),
        content=APIErrorResponse(code=exc.code, message=exc.message, detail=exc.detail).model_dump(),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    code = _code_from_http_status(exc.status_code)
    return JSONResponse(
        status_code=exc.status_code,
        content=APIErrorResponse(code=code, message=exc.detail, detail=None).model_dump(),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content=APIErrorResponse(code=90001, message="Internal server error", detail=str(exc)).model_dump(),
    )


def _http_status_for_code(code: int) -> int:
    prefix = code // 10000
    if prefix == 2:
        return 400
    elif prefix == 3:
        return 401 if code == 30001 else 403
    elif prefix == 5:
        return 404
    return 500


def _code_from_http_status(status: int) -> int:
    mapping = {400: 20001, 401: 30001, 403: 30002, 404: 50001, 409: 20002, 422: 20001, 429: 30003}
    return mapping.get(status, 90001)


@app.get("/")
def read_root():
    return {"message": "Welcome to Dizi Practice Platform API"}


@app.get("/health")
def health_check():
    """Health check endpoint for load balancers and monitoring."""
    return {"status": "healthy"}



# Include API routers
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(scores.router, prefix="/scores", tags=["scores"])
app.include_router(playlists.router, prefix="/playlists", tags=["playlists"])
app.include_router(recordings.router, prefix="/recordings", tags=["recordings"])
app.include_router(debug.router, prefix="/debug", tags=["debug"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
