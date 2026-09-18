"""Classification API. All aggregate writes use the same authorization/transaction service."""
from typing import Literal
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy.orm import Session
from app.core.deps import get_db, get_current_user, get_optional_user
from app.core.classification_errors import ClassificationError
from app.schemas.classification import Envelope, ScoreDetail, ScorePage, ArrangementView, PracticeCapability, Removed, ABCInput, ArrangementInput, CopyInput, LegacyPatch, ScoreCreate, ScorePatch
from app.services import classification as service

router = APIRouter(tags=["scores"])


def ok(data: dict) -> dict:
    return {"code": 0, "message": "ok", "data": data}


def output(result: tuple[dict, str], response: Response) -> dict:
    data, tag = result
    response.headers["ETag"] = tag
    response.headers["Cache-Control"] = "private, no-store"
    return ok(data)


@router.post("/", status_code=201, response_model=Envelope[ScoreDetail], response_model_exclude_unset=True)
def create_score(data: ScoreCreate, response: Response, db: Session = Depends(get_db),
                 user=Depends(get_current_user), idempotency_key: str | None = Header(None)):
    return output(service.create(db, user.id, data, idempotency_key), response)


@router.get("/", response_model=Envelope[ScorePage], response_model_exclude_unset=True)
def list_scores(request: Request, response: Response, scope: Literal["public", "mine"] = "public",
                q: str | None = None, flute_key: str | None = None, fingering: str | None = None,
                match: Literal["any", "whole"] = "any",
                classification: Literal["all", "confirmed", "pending", "needs_review"] = "all",
                page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                db: Session = Depends(get_db), user=Depends(get_optional_user)):
    if "skip" in request.query_params or "limit" in request.query_params:
        raise ClassificationError(422, "INVALID_INPUT", "请使用page/size分页")
    response.headers["Cache-Control"] = "private, no-store"
    return ok(service.listing(db, user.id if user else None, scope, q, flute_key, fingering, match, classification, page, size))


@router.get("/{score_id}", response_model=Envelope[ScoreDetail], response_model_exclude_unset=True)
def read_score(score_id: int, response: Response, db: Session = Depends(get_db), user=Depends(get_optional_user)):
    uid = user.id if user else None
    score = service.accessible(db, score_id, uid)
    return output((service.detail(score, uid), service.etag(score)), response)


@router.patch("/{score_id}", response_model=Envelope[ScoreDetail], response_model_exclude_unset=True)
def patch_score(score_id: int, data: ScorePatch, response: Response, if_match: str | None = Header(None),
                db: Session = Depends(get_db), user=Depends(get_current_user)):
    return output(service.mutate(db, user.id, score_id, "patch", data, if_match), response)


@router.post("/{score_id}/arrangements", status_code=201, response_model=Envelope[ArrangementView], response_model_exclude_unset=True)
def add_arrangement(score_id: int, data: ArrangementInput, response: Response, if_match: str | None = Header(None),
                    idempotency_key: str | None = Header(None), db: Session = Depends(get_db), user=Depends(get_current_user)):
    return output(service.mutate(db, user.id, score_id, "add", data, if_match, idempotency_key), response)


@router.put("/{score_id}/arrangements/{arrangement_id}", response_model=Envelope[ArrangementView], response_model_exclude_unset=True)
def replace_arrangement(score_id: int, arrangement_id: int, data: ArrangementInput, response: Response,
                        if_match: str | None = Header(None), db: Session = Depends(get_db), user=Depends(get_current_user)):
    return output(service.mutate(db, user.id, score_id, "replace", data, if_match, arrangement_id=arrangement_id), response)


@router.delete("/{score_id}/arrangements/{arrangement_id}", response_model=Envelope[Removed])
def remove_arrangement(score_id: int, arrangement_id: int, response: Response, replacement_default_id: int | None = None,
                       if_match: str | None = Header(None), db: Session = Depends(get_db), user=Depends(get_current_user)):
    return output(service.mutate(db, user.id, score_id, "remove", if_match=if_match, arrangement_id=arrangement_id,
                                replacement_default_id=replacement_default_id), response)


@router.get("/{score_id}/arrangements/{arrangement_id}/practice-capability", response_model=Envelope[PracticeCapability])
def practice_capability(score_id: int, arrangement_id: int, db: Session = Depends(get_db), user=Depends(get_optional_user)):
    score = service.accessible(db, score_id, user.id if user else None)
    return ok(service.practice(service.arrangement_for(score, arrangement_id)).model_dump())


@router.post("/{score_id}/publish", response_model=Envelope[ScoreDetail], response_model_exclude_unset=True)
def publish(score_id: int, response: Response, if_match: str | None = Header(None),
            db: Session = Depends(get_db), user=Depends(get_current_user)):
    return output(service.mutate(db, user.id, score_id, "publish", if_match=if_match), response)


@router.post("/{score_id}/unpublish", response_model=Envelope[ScoreDetail], response_model_exclude_unset=True)
def unpublish(score_id: int, response: Response, if_match: str | None = Header(None),
              db: Session = Depends(get_db), user=Depends(get_current_user)):
    return output(service.mutate(db, user.id, score_id, "unpublish", if_match=if_match), response)


@router.post("/{score_id}/copies", status_code=201, response_model=Envelope[ScoreDetail], response_model_exclude_unset=True)
def copy_score(score_id: int, response: Response, data: CopyInput = CopyInput(), idempotency_key: str | None = Header(None),
               db: Session = Depends(get_db), user=Depends(get_current_user)):
    return output(service.mutate(db, user.id, score_id, "copy", data, key=idempotency_key), response)


@router.put("/{score_id}", response_model=Envelope[ScoreDetail], response_model_exclude_unset=True)
def legacy_metadata(score_id: int, data: LegacyPatch, response: Response, if_match: str | None = Header(None),
                    db: Session = Depends(get_db), user=Depends(get_current_user)):
    return output(service.mutate(db, user.id, score_id, "legacy", data, if_match), response)


@router.put("/{score_id}/abc", response_model=Envelope[ScoreDetail], response_model_exclude_unset=True)
def legacy_abc(score_id: int, data: ABCInput, response: Response, if_match: str | None = Header(None),
               db: Session = Depends(get_db), user=Depends(get_current_user)):
    return output(service.mutate(db, user.id, score_id, "abc", data, if_match), response)


@router.delete("/{score_id}")
def legacy_delete(score_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    service.accessible(db, score_id, user.id, write=True)
    # Permanent score/asset deletion is explicitly outside this contract.
    raise ClassificationError(409, "SCORE_DELETE_UNSUPPORTED", "曲目永久删除契约尚未定义；可撤回公开或移除演奏方案")
