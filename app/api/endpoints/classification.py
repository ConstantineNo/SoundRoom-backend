"""Top-level dictionary, candidate and category endpoints."""
from typing import Literal
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from app.core.deps import get_db, get_current_user, get_optional_user
from app.schemas.classification import CandidateInput
from app.services import classification, flute_candidates
from app.api.endpoints.scores import ok

router = APIRouter(tags=["score-classification"])


@router.get("/score-classification-options")
def options():
    return ok(flute_candidates.options())


@router.post("/flute-key-candidates")
def candidates(data: CandidateInput, response: Response, user=Depends(get_current_user)):
    response.headers["Cache-Control"] = "private, no-store"
    return ok(flute_candidates.candidates(data, user.id))


@router.get("/score-categories")
def categories(response: Response, scope: Literal["public", "mine"] = "public", q: str | None = None,
               db: Session = Depends(get_db), user=Depends(get_optional_user)):
    response.headers["Cache-Control"] = "private, no-store"
    return ok(classification.categories(db, user.id if user else None, scope, q))
