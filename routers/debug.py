from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional, Any
import json
import time
import os

router = APIRouter()

LOG_FILE = "debug_logs.jsonl"

class AudioContextInfo(BaseModel):
    sampleRate: float
    state: str
    baseLatency: float
    outputLatency: float

class PitchDebugInfo(BaseModel):
    rms: float
    rawFreq: float
    probability: float
    detectedFreq: float
    processingTimeMs: float

class DebugLog(BaseModel):
    timestamp: float
    userAgent: str
    audioContext: AudioContextInfo
    pitchInfo: Optional[PitchDebugInfo] = None
    rawBuffer: Optional[List[float]] = None # Snapshot of audio buffer
    message: Optional[str] = None

@router.post("/log")
async def create_debug_log(log: DebugLog):
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
