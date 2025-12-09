"""
Bamboo Flute Practice Platform - FastAPI Main Entry Point.

This module initializes the FastAPI application and configures
all middleware, routes, and static file serving.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.database import engine, Base
from app.api.endpoints import auth, scores, playlists, recordings, debug


# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Bamboo Flute Practice Platform")

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files directory
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/")
def read_root():
    """Root endpoint returning welcome message."""
    return {"message": "Welcome to Dizi Practice Platform API"}


# Include API routers
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(scores.router, prefix="/scores", tags=["scores"])
app.include_router(playlists.router, prefix="/playlists", tags=["playlists"])
app.include_router(recordings.router, prefix="/recordings", tags=["recordings"])
app.include_router(debug.router, prefix="/debug", tags=["debug"])
