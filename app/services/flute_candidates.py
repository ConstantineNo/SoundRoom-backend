"""Documented dizi-key-pc-v1 arithmetic; no audio/notation dependencies."""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from app.core.config import SECRET_KEY, ALGORITHM, CLASSIFICATION_CANDIDATE_TTL
from app.core.classification_errors import ClassificationError
from app.schemas.classification import CandidateInput, FingeringInput

RULESET = "dizi-key-pc-v1"
PROFILE = "standard_six_hole_dizi"
KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
KEY_ALIASES = {"C#": ["Db"], "D#": ["Eb"], "F#": ["Gb"], "G#": ["Ab"], "A#": ["Bb"]}
OFFSETS = {"1": 0, "2": 2, "3": 4, "4": 5, "5": 7, "6": 9, "b7": 10, "7": 11}
FINGERINGS = {"closed_" + d: {"code": "closed_" + d, "label": "筒音作" + d.replace("b", "降"),
    "aliases": [p + verb + spelling for p in ("筒音", "全按") for verb in ("作", "做")
                for spelling in (["b7", "♭7", "降7"] if d == "b7" else [d])],
    "inference_supported": True} for d in OFFSETS}


def options() -> dict:
    return {"flute_keys": [{"code": k, "label": k + "调笛", "aliases": KEY_ALIASES.get(k, []), "inference_supported": True} for k in KEYS],
            "fingerings": list(FINGERINGS.values()), "key_notations": ["1=X", "6=Y", "X (assume 1=X)"],
            "ruleset_id": RULESET, "inference_supported": True}


def normalize_fingering(value: FingeringInput) -> tuple[str | None, str | None]:
    if value.code is not None:
        if value.code not in FINGERINGS:
            raise ClassificationError(422, "INVALID_INPUT", "未知指法代码")
        return value.code, None
    raw = value.raw.strip()
    compact = re.sub(r"\s+", "", raw)
    for code, item in FINGERINGS.items():
        if compact in item["aliases"]:
            return code, raw
    return None, raw


def tonic(value: str | None) -> tuple[int | None, list[str]]:
    if not value:
        return None, []
    spelling = re.sub(r"\s+", "", value).replace("♭", "b").replace("♯", "#")
    match = re.fullmatch(r"(?:(1|6)=)?([A-G])([#b]?)", spelling)
    if not match:
        return None, []
    degree, note, accidental = match.groups()
    pc = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[note]
    pc += {"": 0, "#": 1, "b": -1}[accidental]
    return (pc - (9 if degree == "6" else 0)) % 12, ([] if degree else [f"假设1={value}"])


def dependency_input(data: CandidateInput) -> dict:
    code, raw = normalize_fingering(data.fingering)
    selected = getattr(data, data.key_basis + "_key")
    pc, _ = tonic(selected)
    # Only the selected tonal source is a dependency; unrelated keys do not invalidate it.
    return {"key_basis": data.key_basis, "key": selected, "numbered_tonic_pitch_class": pc,
            "fingering": code or raw, "instrument_profile": data.instrument_profile}


def digest(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def infer(data: CandidateInput) -> dict:
    dep = dependency_input(data)
    code, _ = normalize_fingering(data.fingering)
    degree = code.removeprefix("closed_") if code else None
    pc, assumptions = tonic(dep["key"])
    if data.key_basis == "original":
        assumptions.append("按原调作为本段演奏调性")
    if data.instrument_profile == PROFILE:
        assumptions.append("常规六孔竹笛定调约定")
    outcome = "single"
    missing = []
    if data.instrument_profile != PROFILE or not code:
        outcome = "unsupported"
    elif pc is None:
        outcome = "missing_input"
        missing = [data.key_basis + "_key (请明确1=X或6=Y)"]
    candidates = []
    if outcome == "single":
        key = KEYS[(pc + OFFSETS[degree] - 7) % 12]
        candidates = [{"flute_key": key, "label": key + "调笛", "reason": "F=mod12(J+s(f)-7)"}]
    return {"outcome": outcome, "candidates": candidates,
            "normalized_input": {**dep, "original_key": data.original_key, "local_key": data.local_key,
                                 "performance_key": data.performance_key, "closed_degree": int(degree[-1]) if degree else None,
                                 "alteration": -1 if degree == "b7" else 0},
            "assumptions": assumptions, "missing_fields": missing,
            "warnings": [{"reason": "RANGE_NOT_CHECKED"}], "ruleset_id": RULESET,
            "candidate_token": None, "expires_at": None, "range_checked": False}


def candidates(data: CandidateInput, user_id: int) -> dict:
    result = infer(data)
    if result["candidates"]:
        expires = datetime.now(timezone.utc) + timedelta(seconds=CLASSIFICATION_CANDIDATE_TTL)
        result["candidate_token"] = jwt.encode({"sub": str(user_id), "purpose": "flute_candidate",
            "input": digest(dependency_input(data)), "keys": [c["flute_key"] for c in result["candidates"]],
            "ruleset": RULESET, "exp": expires}, SECRET_KEY, algorithm=ALGORITHM)
        result["expires_at"] = expires.isoformat()
    return result


def verify_candidate(token: str, data: CandidateInput, key: str, user_id: int) -> None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        valid = (payload.get("purpose") == "flute_candidate" and payload.get("sub") == str(user_id)
                 and payload.get("input") == digest(dependency_input(data)) and payload.get("ruleset") == RULESET
                 and key in payload.get("keys", []) and "exp" in payload)
    except JWTError:
        valid = False
    if not valid:
        raise ClassificationError(409, "CANDIDATE_STALE")
