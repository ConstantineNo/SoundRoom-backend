"""Debug endpoints for logging and diagnostics."""

import json
import time
import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


router = APIRouter(tags=["debug"])

LOG_FILE = "debug_logs.jsonl"


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


@router.post("/log")
async def create_debug_log(log: DebugLog):
    """Store a debug log entry."""
    try:
        entry = log.dict()
        entry["server_received_at"] = time.time()
        
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        
        return {"status": "ok", "saved_to": LOG_FILE}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs")
async def get_debug_logs(limit: int = 10):
    """Get recent debug logs."""
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
