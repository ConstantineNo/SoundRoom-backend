from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base
from routers import auth, scores, playlists, recordings, debug
from fastapi.staticfiles import StaticFiles

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Bamboo Flute Practice Platform")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

@app.get("/")
def read_root():
    return {"message": "Welcome to Dizi Practice Platform API"}

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(scores.router, prefix="/api/scores", tags=["scores"])
app.include_router(playlists.router, prefix="/api/playlists", tags=["playlists"])
app.include_router(recordings.router, prefix="/api/recordings", tags=["recordings"])
app.include_router(debug.router, prefix="/api/debug", tags=["debug"])
