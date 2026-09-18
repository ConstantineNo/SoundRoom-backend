"""Persistence and permission-scoped SQL queries for classification."""
from datetime import datetime
from sqlalchemy import and_, exists, func, or_, select, text
from sqlalchemy.orm import Session, selectinload
from app.models.score import Score
from app.models.classification import Arrangement, Section, IdempotencyRecord


def begin_write(db: Session) -> None:
    # The configured application is SQLite-backed. This database lock serializes
    # ETag/idempotency read-modify-write transactions across worker processes.
    db.execute(text("BEGIN IMMEDIATE"))
    db.expire_all()


def get_score(db: Session, score_id: int) -> Score | None:
    return db.scalar(select(Score).where(Score.id == score_id).options(
        selectinload(Score.arrangements).selectinload(Arrangement.sections), selectinload(Score.assets)))


def scope_query(owner_id: int | None, q: str | None = None):
    query = select(Score).where(Score.visibility == "public" if owner_id is None else Score.created_by == owner_id)
    q = q.strip() if q else None
    if q:
        tags = func.json_each(Score.tags).table_valued("value")
        query = query.where(or_(
            *(func.lower(column).contains(q.lower(), autoescape=True) for column in (
                Score.title, Score.edition_label, Score.edition_original_artist, Score.edition_performer, Score.edition_album)),
            exists(select(1).select_from(tags).where(func.lower(tags.c.value).contains(q.lower(), autoescape=True)))))
    return query


def confirmed_condition():
    return and_(Section.classification_status == "confirmed", Section.flute_key.is_not(None), Section.fingering_code.is_not(None))


def page_scores(db: Session, owner_id: int | None, q: str | None, flute_key: str | None,
                fingering: str | None, match: str, classification: str, page: int, size: int) -> tuple[list[Score], int]:
    query = scope_query(owner_id, q)
    if classification == "confirmed":
        query = query.where(Score.arrangements.any(), ~Score.arrangements.any(or_(
            ~Arrangement.sections.any(), Arrangement.sections.any(~confirmed_condition()))))
    elif classification in ("pending", "needs_review"):
        query = query.where(Score.arrangements.any(Arrangement.sections.any(Section.classification_status == classification)))
    if flute_key:
        condition = and_(confirmed_condition(), Section.flute_key == flute_key)
        if fingering:
            condition = and_(condition, Section.fingering_code == fingering)
        if match == "whole":
            query = query.where(Score.arrangements.any(and_(Arrangement.coverage == "complete",
                Arrangement.sections.any(), ~Arrangement.sections.any(~condition))))
        else:
            query = query.where(Score.arrangements.any(Arrangement.sections.any(condition)))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = list(db.scalars(query.options(selectinload(Score.arrangements).selectinload(Arrangement.sections))
        .order_by(Score.updated_at.desc(), Score.id.desc()).offset((page-1)*size).limit(size)))
    return items, total


def category_counts(db: Session, owner_id: int | None, q: str | None) -> dict:
    visible = scope_query(owner_id, q).with_only_columns(Score.id).subquery()
    base = select(Section.flute_key, Section.fingering_code, func.count(func.distinct(Arrangement.score_id)))\
        .join(Arrangement, Section.arrangement_id == Arrangement.id).join(visible, Arrangement.score_id == visible.c.id)
    confirmed = base.where(confirmed_condition())
    groups = db.execute(confirmed.group_by(Section.flute_key, Section.fingering_code)).all()
    keys = db.execute(confirmed.with_only_columns(Section.flute_key, func.count(func.distinct(Arrangement.score_id)))
        .group_by(Section.flute_key)).all()
    count = func.count(func.distinct(Arrangement.score_id))
    return {"groups": groups, "keys": dict(keys),
        "total_visible_scores": db.scalar(select(func.count()).select_from(visible)),
        "classified_score_count": db.scalar(confirmed.with_only_columns(count)),
        "pending_score_count": db.scalar(base.with_only_columns(count).where(Section.classification_status == "pending")),
        "review_score_count": db.scalar(base.with_only_columns(count).where(Section.classification_status == "needs_review"))}


def retry_record(db: Session, user_id: int, path: str, key: str) -> IdempotencyRecord | None:
    record = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.user_id == user_id,
        IdempotencyRecord.method == "POST", IdempotencyRecord.path == path, IdempotencyRecord.key == key))
    if record and record.expires_at <= datetime.utcnow():
        db.delete(record)
        db.flush()
        return None
    return record


def save(db: Session, value) -> None:
    db.add(value)


def flush(db: Session) -> None:
    db.flush()


def commit(db: Session) -> None:
    db.commit()
