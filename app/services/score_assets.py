"""Optional, private assets; parsing never grants practice capability."""
from datetime import datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import hashlib
import wave
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session
from app.core.config import CLASSIFICATION_ASSET_DIR, CLASSIFICATION_MAX_ASSET_SIZE, UPLOAD_DIR
from app.core.classification_errors import ClassificationError as Error
from app.crud import classification as store
from app.models.classification import ScoreAsset
from app.schemas.classification import NotationBindings
from app.services import classification as scores


def validate_content(content: bytes, purpose: str) -> tuple[str, str, list]:
    if not content:
        raise Error(422, "INVALID_INPUT", "文件为空")
    if len(content) > CLASSIFICATION_MAX_ASSET_SIZE:
        raise Error(413, "FILE_TOO_LARGE")
    if purpose == "score_image":
        try:
            with Image.open(BytesIO(content)) as image:
                if image.format not in ("PNG", "JPEG"):
                    raise Error(415, "UNSUPPORTED_MEDIA")
                media_type = Image.MIME[image.format]
                image.verify()
            return media_type, "stored", []
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            raise Error(415, "UNSUPPORTED_MEDIA", "仅支持经过验证的PNG/JPEG谱图")
    if purpose == "reference_audio":
        try:
            with wave.open(BytesIO(content), "rb") as audio:
                if audio.getcomptype() != "NONE" or not audio.getnframes() or audio.getnchannels() not in (1, 2):
                    raise ValueError()
                expected = audio.getnframes() * audio.getnchannels() * audio.getsampwidth()
                if len(audio.readframes(audio.getnframes())) != expected:
                    raise ValueError()
            return "audio/wav", "stored", []
        except (wave.Error, EOFError, ValueError):
            raise Error(415, "UNSUPPORTED_MEDIA", "参考音频当前支持单/双声道PCM WAV")
    if purpose == "machine_notation":
        try:
            source = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise Error(415, "UNSUPPORTED_MEDIA", "机器谱当前支持UTF-8 ABC")
        if "\x00" in source or not any(line.startswith("K:") for line in source.splitlines()):
            raise Error(415, "UNSUPPORTED_MEDIA", "机器谱当前支持UTF-8 ABC")
        # Store safely, without synchronous parsing or a claim of readiness. The
        # existing parser does not validate practice targets/part/measure identity.
        return "text/vnd.abc; charset=utf-8", "stored", [{"reason": "NOTATION_NOT_VERIFIED"}]
    raise Error(422, "INVALID_INPUT", "未知资料用途")


def asset_for(score, asset_id: int) -> ScoreAsset:
    asset = next((a for a in score.assets if a.id == asset_id), None)
    if not asset:
        raise Error(404, "NOT_FOUND")
    return asset


def upload(db: Session, user_id: int, score_id: int, content: bytes, purpose: str,
           arrangement_id: int | None, if_match: str | None, key: str | None) -> tuple[dict, str]:
    store.begin_write(db)
    score = scores.accessible(db, score_id, user_id, write=True)
    if arrangement_id is not None:
        scores.arrangement_for(score, arrangement_id)
    if purpose == "machine_notation" and arrangement_id is None:
        raise Error(422, "INVALID_INPUT", "机器谱必须关联演奏方案")
    payload = {"purpose": purpose, "arrangement_id": arrangement_id, "sha256": hashlib.sha256(content).hexdigest()}
    path = f"/scores/{score_id}/assets"
    replay = scores.retry(db, user_id, path, key, payload)
    if replay:
        result = replay.response, replay.etag
        store.commit(db)
        return result
    scores.check_version(score, if_match)
    media_type, status, issues = validate_content(content, purpose)
    root = Path(CLASSIFICATION_ASSET_DIR)
    root.mkdir(parents=True, exist_ok=True)
    storage_key = uuid4().hex
    target = root / storage_key
    asset = ScoreAsset(purpose=purpose, arrangement_id=arrangement_id, storage_key=storage_key,
        media_type=media_type, size=len(content), processing_status=status, issues=issues,
        public_allowed=False, copy_allowed=False, created_at=datetime.utcnow())
    score.assets.append(asset)
    scores.touch(score)
    try:
        with target.open("xb") as stream:
            stream.write(content)
        store.flush(db)
        return scores.finish(db, score, scores.asset_view(asset), (user_id, path, key, payload))
    except Exception:
        db.rollback()
        if target.exists():
            recycle = root / "recycle"
            recycle.mkdir(exist_ok=True)
            target.rename(recycle / storage_key)
        raise


def content(db: Session, user_id: int | None, score_id: int, asset_id: int) -> tuple[Path, str]:
    score = scores.accessible(db, score_id, user_id)
    asset = asset_for(score, asset_id)
    if user_id != score.created_by and not asset.public_allowed:
        raise Error(404, "NOT_FOUND")
    if asset.legacy_path:
        root = Path(UPLOAD_DIR).resolve()
        legacy = asset.legacy_path
        if legacy.startswith("/uploads/"):
            path = (root / legacy.removeprefix("/uploads/")).resolve()
        else:
            path = Path(legacy).resolve()
    else:
        root = Path(CLASSIFICATION_ASSET_DIR).resolve()
        path = (root / asset.storage_key).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise Error(404, "NOT_FOUND")
    return path, asset.media_type


def remove(db: Session, user_id: int, score_id: int, asset_id: int, if_match: str | None) -> tuple[dict, str]:
    store.begin_write(db)
    score = scores.accessible(db, score_id, user_id, write=True)
    asset = asset_for(score, asset_id)
    scores.check_version(score, if_match)
    score.assets.remove(asset)
    scores.touch(score)
    store.flush(db)
    # Retain the physical object: an independent copy may still reference it.
    return scores.finish(db, score, {"removed_id": asset_id})


def bindings(db: Session, user_id: int, score_id: int, arrangement_id: int,
             data: NotationBindings, if_match: str | None) -> None:
    store.begin_write(db)
    score = scores.accessible(db, score_id, user_id, write=True)
    arrangement = scores.arrangement_for(score, arrangement_id)
    asset = asset_for(score, data.notation_asset_id)
    if asset.arrangement_id != arrangement_id or asset.purpose != "machine_notation":
        raise Error(404, "NOT_FOUND")
    ids = [b.section_id for b in data.bindings]
    if len(ids) != len(set(ids)):
        raise Error(422, "INVALID_INPUT", "重复段落绑定")
    if any(i not in {s.id for s in arrangement.sections} for i in ids):
        raise Error(404, "NOT_FOUND")
    scores.check_version(score, if_match)
    # Reserved contract: the existing ABC parser cannot certify measure/part
    # identities or calibrated targets. Never accept integer ranges as proof.
    raise Error(409, "NOTATION_NOT_READY", "谱面定位及跟练目标验证尚未接入")
