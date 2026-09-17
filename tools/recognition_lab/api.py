"""Optional localhost-only HTTP harness, deliberately separate from app.main."""
from .runtime import configure_runtime
configure_runtime()

import asyncio
from io import BytesIO
from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from app.schemas.audio_recognition import RecognitionConfig, RecognitionResult
from app.services.audio_recognition import analyze, load_audio, AudioInputError
from app.services.audio_recognition.audio import MAX_BYTES

api = FastAPI(title="SoundRoom local recognition", version="1.0")
lock = asyncio.Lock()


@api.post("/recognize", response_model=RecognitionResult)
async def recognize(request: Request, params: str | None = None):
    """Raw audio body; optional JSON config query. Bounded before decoding, no temp file."""
    try:
        config = RecognitionConfig.model_validate_json(params) if params else RecognitionConfig()
    except ValidationError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    if lock.locked():
        raise HTTPException(429, detail="Recognition busy; retry after the current analysis")
    async with lock:
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > MAX_BYTES:
                raise HTTPException(413, detail="Audio body exceeds 32 MiB")
            data.extend(chunk)
        try:
            def process():
                return analyze(load_audio(BytesIO(data)), config)
            return await run_in_threadpool(process)
        except AudioInputError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
