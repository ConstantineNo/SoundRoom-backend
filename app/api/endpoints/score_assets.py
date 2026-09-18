"""Optional assets and reserved notation binding adapter."""
from typing import Literal
from fastapi import APIRouter, Depends, File, Form, Header, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.core.deps import get_db, get_current_user, get_optional_user
from app.core.config import CLASSIFICATION_MAX_ASSET_SIZE
from app.schemas.classification import Envelope, AssetView, Removed, NotationBindings
from app.services import score_assets
from app.api.endpoints.scores import output

router = APIRouter(tags=["score-assets"])


@router.post("/{score_id}/assets", status_code=201, response_model=Envelope[AssetView])
def upload_asset(score_id: int, response: Response, file: UploadFile = File(...),
                 purpose: Literal["score_image", "reference_audio", "machine_notation"] = Form(...),
                 arrangement_id: int | None = Form(None), if_match: str | None = Header(None),
                 idempotency_key: str | None = Header(None), db: Session = Depends(get_db), user=Depends(get_current_user)):
    content = file.file.read(CLASSIFICATION_MAX_ASSET_SIZE + 1)
    return output(score_assets.upload(db, user.id, score_id, content, purpose, arrangement_id, if_match, idempotency_key), response)


@router.get("/{score_id}/assets/{asset_id}")
def read_asset(score_id: int, asset_id: int, db: Session = Depends(get_db), user=Depends(get_optional_user)):
    path, media_type = score_assets.content(db, user.id if user else None, score_id, asset_id)
    extension = {"image/png": "png", "image/jpeg": "jpg", "audio/wav": "wav", "text/vnd.abc; charset=utf-8": "abc", "application/octet-stream": "bin"}[media_type]
    return FileResponse(path, media_type=media_type, filename=f"score-asset-{asset_id}.{extension}",
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.delete("/{score_id}/assets/{asset_id}", response_model=Envelope[Removed])
def remove_asset(score_id: int, asset_id: int, response: Response, if_match: str | None = Header(None),
                 db: Session = Depends(get_db), user=Depends(get_current_user)):
    return output(score_assets.remove(db, user.id, score_id, asset_id, if_match), response)


@router.put("/{score_id}/arrangements/{arrangement_id}/notation-bindings")
def update_bindings(score_id: int, arrangement_id: int, data: NotationBindings, if_match: str | None = Header(None),
                    db: Session = Depends(get_db), user=Depends(get_current_user)):
    score_assets.bindings(db, user.id, score_id, arrangement_id, data, if_match)
