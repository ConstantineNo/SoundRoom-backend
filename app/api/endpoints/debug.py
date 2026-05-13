"""Debug endpoints for logging and diagnostics.

These endpoints are gated by DIZI_DEBUG_ENABLED=true env var.
They MUST NOT be enabled in production.
"""

import json
import time
import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import DEBUG_ENABLED

router = APIRouter(tags=["debug"])

LOG_FILE = "debug_logs.jsonl"
MAX_LOG_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


class AudioContextInfo(BaseModel):
    """Audio context information from client."""
    sampleRate: float
    state: str
    baseLatency: float
    outputLatency: float


class PitchDebugInfo(BaseModel):
    """Pitch detection debug information."""
    rms: float
    rawFreq: float
    probability: float
    detectedFreq: float
    processingTimeMs: float


class DebugLog(BaseModel):
    """Debug log entry from client."""
    timestamp: float
    userAgent: str
    audioContext: AudioContextInfo
    pitchInfo: Optional[PitchDebugInfo] = None
    rawBuffer: Optional[List[float]] = None
    message: Optional[str] = None


def _debug_disabled():
    raise HTTPException(status_code=404, detail="Debug endpoint not available")


@router.post("/log")
async def create_debug_log(log: DebugLog):
    """Store a debug log entry. Only available when DIZI_DEBUG_ENABLED=true."""
    if not DEBUG_ENABLED:
        return _debug_disabled()
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > MAX_LOG_FILE_SIZE:
            raise HTTPException(status_code=400, detail="Debug log file is full")

        entry = log.model_dump()
        entry["server_received_at"] = time.time()

        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        return {"status": "ok", "saved_to": LOG_FILE}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs")
async def get_debug_logs(limit: int = 10):
    """Get recent debug logs. Only available when DIZI_DEBUG_ENABLED=true."""
    if not DEBUG_ENABLED:
        return _debug_disabled()
    logs = []
    if not os.path.exists(LOG_FILE):
        return []

    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            for line in lines[-limit:]:
                logs.append(json.loads(line))
        return logs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
