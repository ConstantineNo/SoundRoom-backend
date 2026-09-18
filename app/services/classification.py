"""Score classification aggregate, authorization and transactional mutations."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from app.core.classification_errors import ClassificationError as Error
from app.core.config import CLASSIFICATION_IDEMPOTENCY_TTL
from app.crud import classification as store
from app.models.score import Score
from app.models.classification import Arrangement, Section, IdempotencyRecord, ScoreAsset
from app.schemas.classification import (ArrangementInput, ArrangementView, CandidateInput, ClassificationDecision,
    AssetView, EditionMetadata, FingeringInput, ScoreCreate, ScoreDetail, ScorePatch, ScoreSummary, SectionInput, SectionView, PracticeCapability)
from app.services import flute_candidates as rules


def edition_view(score: Score) -> dict:
    return EditionMetadata(**{name: getattr(score, "edition_" + name) for name in EditionMetadata.model_fields}).model_dump()


def apply_edition(score: Score, value: EditionMetadata | None) -> None:
    updates = value.model_dump(exclude_unset=True) if value is not None else {name: None for name in EditionMetadata.model_fields}
    for name, text in updates.items():
        setattr(score, "edition_" + name, text)


def replay_response(record: IdempotencyRecord) -> dict:
    response = deepcopy(record.response)
    if "arrangements" in response and "owner" in response and "edition" not in response:
        # Older creation/copy receipts describe an empty edition, not today's edited value.
        response["edition"] = EditionMetadata().model_dump()
    return response


def etag(score: Score) -> str:
    return f'"score-{score.id}-{score.revision}"'


def accessible(db: Session, score_id: int, user_id: int | None, write: bool = False) -> Score:
    score = store.get_score(db, score_id)
    if not score or (score.created_by != user_id and score.visibility != "public") or (score.created_by is None and score.visibility != "public"):
        raise Error(404, "NOT_FOUND")
    if write and score.created_by != user_id:
        raise Error(403, "OWNER_REQUIRED")
    return score


def arrangement_for(score: Score, arrangement_id: int) -> Arrangement:
    for arrangement in score.arrangements:
        if arrangement.id == arrangement_id:
            return arrangement
    raise Error(404, "NOT_FOUND")


def confirmed(section: Section) -> bool:
    return section.classification_status == "confirmed" and section.flute_key in rules.KEYS and section.fingering_code in rules.FINGERINGS


def facts(arrangement: Arrangement) -> dict:
    sections = arrangement.sections
    complete = bool(sections) and all(confirmed(s) for s in sections)
    keys = {s.flute_key for s in sections if confirmed(s)}
    fingerings = {s.fingering_code for s in sections if confirmed(s)}
    return {"classification_complete": complete,
            "requires_flute_switch": True if len(keys) > 1 else (False if complete else None),
            "requires_fingering_switch": True if len(fingerings) > 1 else (False if complete else None)}


def practice(arrangement: Arrangement) -> PracticeCapability:
    notation = next((a for a in arrangement.score.assets if a.arrangement_id == arrangement.id and a.purpose == "machine_notation"), None)
    if notation:
        return PracticeCapability(status="unavailable" if notation.processing_status == "failed" else "unverified",
            available=False, notation_asset_id=notation.id, reasons=["NOTATION_NOT_VERIFIED"])
    # Legacy ABC is unverified, and can only be attributed to a unique arrangement.
    if len(arrangement.score.arrangements) == 1 and arrangement.score.abc_source:
        return PracticeCapability(status="unverified", available=False, notation_asset_id=None, reasons=["NOTATION_NOT_VERIFIED"])
    return PracticeCapability(status="not_provided", available=False, notation_asset_id=None, reasons=["NOTATION_NOT_PROVIDED"])


def arrangement_view(arrangement: Arrangement, owner: bool) -> dict:
    sections = []
    for s in sorted(arrangement.sections, key=lambda item: item.position):
        value = {key: getattr(s, key) for key in ("id", "position", "location_label", "local_key", "performance_key",
                  "key_basis", "instrument_profile", "notes", "classification_status")}
        value.update(fingering={"code": s.fingering_code, "label": rules.FINGERINGS.get(s.fingering_code, {}).get("label"), "raw": s.fingering_raw},
                     flute_key=s.flute_key if confirmed(s) else None)
        if owner:
            value["classification_evidence"] = s.evidence or {}
        sections.append(SectionView(**value).model_dump(exclude_unset=True))
    return ArrangementView(id=arrangement.id, label=arrangement.label, coverage=arrangement.coverage,
        is_default=arrangement.is_default, notes=arrangement.notes, sections=sections,
        practice_capability=practice(arrangement), **facts(arrangement)).model_dump(exclude_unset=True)


def summary(score: Score) -> dict:
    timestamp = score.updated_at
    return ScoreSummary(edition=edition_view(score), id=score.id, title=score.title, original_key=score.original_key, notes=score.notes,
        tags=score.tags or [], owner={"id": score.created_by}, visibility=score.visibility,
        classification_incomplete=not score.arrangements or any(not facts(a)["classification_complete"] for a in score.arrangements),
        updated_at=timestamp.replace(tzinfo=timezone.utc).isoformat() if timestamp else None).model_dump(exclude_unset=True)


def detail(score: Score, user_id: int | None) -> dict:
    return ScoreDetail(**summary(score), arrangements=[arrangement_view(a, score.created_by == user_id and user_id is not None)
        for a in score.arrangements], assets=[asset_view(a) for a in score.assets if a.public_allowed or score.created_by == user_id]).model_dump(exclude_unset=True)


def conditions(score: Score, section: Section) -> CandidateInput:
    return CandidateInput(original_key=score.original_key or "", local_key=section.local_key,
        performance_key=section.performance_key, key_basis=section.key_basis, instrument_profile=section.instrument_profile,
        fingering=FingeringInput(code=section.fingering_code) if section.fingering_code else FingeringInput(raw=section.fingering_raw or "未知"))


def invalidate(section: Section, data: CandidateInput) -> None:
    evidence = deepcopy(section.evidence or {})
    if section.classification_status in ("confirmed", "needs_review"):
        if section.flute_key:
            evidence["previous_flute_key"] = section.flute_key
        section.flute_key = None
        section.classification_status = "needs_review"
    evidence["current_inference"] = rules.infer(data)
    section.evidence = evidence


def set_section(score: Score, section: Section, data: SectionInput, position: int, user_id: int, new: bool) -> None:
    before = None if new else rules.dependency_input(conditions(score, section))
    code, raw = rules.normalize_fingering(data.fingering)
    for name in ("location_label", "local_key", "performance_key", "key_basis", "instrument_profile", "notes"):
        setattr(section, name, getattr(data, name))
    section.position, section.fingering_code, section.fingering_raw = position, code, raw
    if new:
        section.classification_status, section.evidence = "pending", {}
    inputs = conditions(score, section)
    if not new and before != rules.dependency_input(inputs):
        invalidate(section, inputs)
    decision = data.classification_decision
    if decision:
        if decision.flute_key not in rules.KEYS or code is None:
            raise Error(422, "INVALID_INPUT", "确认需要规范笛调和指法")
        if decision.method == "candidate":
            rules.verify_candidate(decision.candidate_token, inputs, decision.flute_key, user_id)
        inference = rules.infer(inputs)
        warnings = []
        if not inference["candidates"]:
            warnings.append({"reason": "RELATION_NOT_CHECKED"})
        elif decision.flute_key not in [c["flute_key"] for c in inference["candidates"]]:
            warnings.append({"reason": "KEY_RELATION_MISMATCH"})
        section.evidence = {"method": decision.method, "confirmed_input": rules.dependency_input(inputs),
                            "inference": inference, "warnings": warnings}
        section.flute_key, section.classification_status = decision.flute_key, "confirmed"


def set_arrangement(score: Score, arrangement: Arrangement, data: ArrangementInput, user_id: int, new: bool) -> None:
    existing = {s.id: s for s in arrangement.sections}
    ids = [s.id for s in data.sections if s.id is not None]
    if len(set(ids)) != len(ids):
        raise Error(422, "INVALID_INPUT", "段落 id 重复")
    if any(i not in existing for i in ids):
        raise Error(404, "NOT_FOUND")
    if data.is_default is True:
        for other in score.arrangements:
            other.is_default = False
        arrangement.is_default = True
    elif data.is_default is False and arrangement.is_default:
        raise Error(409, "DEFAULT_REPLACEMENT_REQUIRED")
    elif new:
        arrangement.is_default = False
    arrangement.label, arrangement.coverage, arrangement.notes = data.label, data.coverage, data.notes
    sections = []
    for position, value in enumerate(data.sections):
        section = existing.get(value.id) if value.id else Section()
        set_section(score, section, value, position, user_id, value.id is None)
        sections.append(section)
    arrangement.sections = sections


def patch_score(score: Score, data: ScorePatch) -> None:
    old_key = score.original_key
    for key, value in data.model_dump(exclude_unset=True, exclude={"edition"}).items():
        setattr(score, key, value)
    if "edition" in data.model_fields_set:
        apply_edition(score, data.edition)
    if score.original_key != old_key:
        for a in score.arrangements:
            for s in a.sections:
                if s.key_basis == "original":
                    invalidate(s, conditions(score, s))


def check_version(score: Score, if_match: str | None) -> None:
    if not if_match:
        raise Error(428, "PRECONDITION_REQUIRED")
    if if_match != etag(score):
        raise Error(412, "EDIT_CONFLICT")


def retry(db: Session, user_id: int, path: str, key: str | None, payload: dict):
    if not key or not key.strip() or len(key) > 200:
        raise Error(422, "INVALID_INPUT", "需要有效 Idempotency-Key（1–200字符）")
    record = store.retry_record(db, user_id, path, key)
    if record and record.digest != rules.digest(payload):
        raise Error(409, "IDEMPOTENCY_CONFLICT")
    if record and path == "/scores/":
        accessible(db, record.response["id"], user_id, write=True)
    return record


def finish(db: Session, score: Score, result: dict, retry_args: tuple | None = None) -> tuple[dict, str]:
    tag = etag(score)
    if retry_args:
        user_id, path, key, payload = retry_args
        store.save(db, IdempotencyRecord(user_id=user_id, method="POST", path=path, key=key,
            digest=rules.digest(payload), response=result, etag=tag,
            expires_at=datetime.utcnow() + timedelta(seconds=CLASSIFICATION_IDEMPOTENCY_TTL)))
    store.commit(db)
    return result, tag


def touch(score: Score) -> None:
    score.revision += 1
    score.updated_at = datetime.utcnow()
    # Legacy scalar fields are no longer a second source of classification truth.
    score.song_key = None
    score.flute_key = None
    score.fingering = None


def create(db: Session, user_id: int, data: ScoreCreate, key: str | None) -> tuple[dict, str]:
    store.begin_write(db)
    payload, path = data.model_dump(mode="json"), "/scores/"
    if data.edition is None or not any(value is not None for value in data.edition.model_dump().values()):
        # Keep pre-edition request digests valid across the rolling schema upgrade.
        payload.pop("edition")
    replay = retry(db, user_id, path, key, payload)
    if replay:
        result = replay_response(replay), replay.etag
        store.commit(db)
        return result
    score = Score(title=data.title, original_key=data.original_key, notes=data.notes, tags=data.tags,
                  created_by=user_id, visibility="private", revision=1)
    apply_edition(score, data.edition)
    arrangement = Arrangement(label="默认方案", coverage="complete", is_default=True)
    score.arrangements = [arrangement]
    section = Section()
    set_section(score, section, SectionInput(location_label="全曲", fingering=data.fingering,
        instrument_profile=data.instrument_profile, classification_decision=data.classification_decision), 0, user_id, True)
    arrangement.sections = [section]
    store.save(db, score)
    store.flush(db)
    return finish(db, score, detail(score, user_id), (user_id, path, key, payload))


def mutate(db: Session, user_id: int, score_id: int, operation: str, data=None,
           if_match: str | None = None, key: str | None = None, arrangement_id: int | None = None,
           replacement_default_id: int | None = None) -> tuple[dict, str]:
    store.begin_write(db)
    score = accessible(db, score_id, user_id, write=operation != "copy")
    arrangement = arrangement_for(score, arrangement_id) if arrangement_id is not None else None
    retry_args = None
    if operation in ("add", "copy"):
        path = f"/scores/{score_id}/" + ("arrangements" if operation == "add" else "copies")
        payload = data.model_dump(mode="json")
        replay = retry(db, user_id, path, key, payload)
        if replay:
            result = replay_response(replay), replay.etag
            store.commit(db)
            return result
        retry_args = (user_id, path, key, payload)
    if operation != "copy":
        check_version(score, if_match)
    if operation == "patch":
        patch_score(score, data)
    elif operation == "add":
        arrangement = Arrangement()
        set_arrangement(score, arrangement, data, user_id, True)
        score.arrangements.append(arrangement)
    elif operation == "replace":
        set_arrangement(score, arrangement, data, user_id, False)
    elif operation == "remove":
        if len(score.arrangements) == 1:
            raise Error(409, "LAST_ARRANGEMENT")
        if arrangement.is_default:
            if replacement_default_id is None or replacement_default_id == arrangement_id:
                raise Error(409, "DEFAULT_REPLACEMENT_REQUIRED")
            arrangement_for(score, replacement_default_id).is_default = True
        for asset in score.assets:
            if asset.arrangement_id == arrangement_id:
                asset.arrangement_id = None
        store.flush(db)
        score.arrangements.remove(arrangement)
    elif operation in ("publish", "unpublish"):
        score.visibility = "public" if operation == "publish" else "private"
    elif operation == "copy":
        source = score
        score = Score(title=data.title or source.title, original_key=source.original_key, notes=source.notes,
            tags=deepcopy(source.tags), created_by=user_id, visibility="private", revision=1)
        apply_edition(score, EditionMetadata(**edition_view(source)))
        for a in source.arrangements:
            copied = Arrangement(label=a.label, coverage=a.coverage, is_default=a.is_default, notes=a.notes)
            for s in a.sections:
                fields = {field: getattr(s, field) for field in ("position", "location_label", "local_key", "performance_key",
                    "key_basis", "instrument_profile", "fingering_code", "fingering_raw", "flute_key", "classification_status", "notes")}
                # Do not expose/reuse the other owner's candidate evidence.
                copied.sections.append(Section(**fields, evidence={"source_score_id": source.id, "method": "copy"}))
            score.arrangements.append(copied)
        for asset in source.assets:
            if asset.public_allowed and asset.copy_allowed and asset.purpose != "reference_audio":
                score.assets.append(ScoreAsset(purpose=asset.purpose, storage_key=asset.storage_key, legacy_path=asset.legacy_path, media_type=asset.media_type,
                    size=asset.size, processing_status=asset.processing_status, issues=deepcopy(asset.issues),
                    public_allowed=False, copy_allowed=False, created_at=datetime.utcnow()))
        store.save(db, score)
    elif operation == "legacy":
        values = data.model_dump(exclude_unset=True)
        if not values or any(v is None for v in values.values()):
            raise Error(422, "INVALID_INPUT")
        if "flute_key" in values or "fingering" in values:
            if len(score.arrangements) != 1 or len(score.arrangements[0].sections) != 1 or score.arrangements[0].coverage != "complete":
                raise Error(409, "LEGACY_AMBIGUOUS")
        patch = {("original_key" if k == "song_key" else k): v for k, v in values.items() if k in ("title", "song_key", "tags")}
        # Capture old confirmation before key invalidation for an explicit legacy decision.
        single = score.arrangements[0].sections[0] if len(score.arrangements) == 1 and len(score.arrangements[0].sections) == 1 else None
        old_key = single.flute_key if single else None
        if patch:
            patch_score(score, ScorePatch(**patch))
        if "flute_key" in values or "fingering" in values:
            flute = values.get("flute_key", old_key)
            if not flute:
                raise Error(422, "INVALID_INPUT", "需要 flute_key 才能明确确认")
            finger = values.get("fingering")
            finger_input = (FingeringInput(code=finger) if finger in rules.FINGERINGS else FingeringInput(raw=finger)) if finger else conditions(score, single).fingering
            section_data = SectionInput(**{name: getattr(single, name) for name in ("location_label", "local_key", "performance_key", "key_basis", "instrument_profile", "notes")},
                fingering=finger_input, classification_decision=ClassificationDecision(method="manual", flute_key=flute))
            set_section(score, single, section_data, 0, user_id, False)
    elif operation == "abc":
        if len(score.arrangements) != 1:
            raise Error(409, "LEGACY_AMBIGUOUS")
        from app.services.score_service import parse_abc_to_json
        score.abc_source = data.abc_content
        try:
            score.structured_data = parse_abc_to_json(score.abc_source)
        except ValueError:
            raise Error(422, "INVALID_INPUT", "无法解析ABC")
    else:
        raise Error(422, "INVALID_INPUT")
    if operation != "copy":
        touch(score)
    store.flush(db)
    if operation in ("add", "replace"):
        result = arrangement_view(arrangement, True)
    elif operation == "remove":
        result = {"removed_id": arrangement_id}
    else:
        result = detail(score, user_id)
    return finish(db, score, result, retry_args)


def scope_owner(scope: str, user_id: int | None) -> int | None:
    if scope == "mine" and user_id is None:
        raise Error(401, "AUTH_REQUIRED")
    return user_id if scope == "mine" else None


def matching(arrangement: Arrangement, flute_key: str, fingering: str | None) -> dict | None:
    ids = [s.id for s in arrangement.sections if confirmed(s) and s.flute_key == flute_key and (not fingering or s.fingering_code == fingering)]
    if not ids:
        return None
    combos = list(dict.fromkeys((s.flute_key, s.fingering_code) for s in arrangement.sections if confirmed(s)))
    return {"arrangement_id": arrangement.id, "section_ids": ids,
            "whole_match": arrangement.coverage == "complete" and len(ids) == len(arrangement.sections),
            "required_combinations": [{"flute_key": k, "fingering": f} for k, f in combos], **facts(arrangement)}


def listing(db: Session, user_id: int | None, scope="public", q=None, flute_key=None, fingering=None,
            match="any", classification="all", page=1, size=20) -> dict:
    if flute_key is not None and flute_key not in rules.KEYS or fingering is not None and fingering not in rules.FINGERINGS:
        raise Error(422, "INVALID_INPUT")
    if (fingering and not flute_key) or (match == "whole" and not (fingering and flute_key)) or (classification != "all" and scope != "mine"):
        raise Error(422, "INVALID_INPUT")
    scores, total = store.page_scores(db, scope_owner(scope, user_id), q, flute_key, fingering, match, classification, page, size)
    items = []
    for score in scores:
        value = summary(score)
        if flute_key:
            value["matched_arrangements"] = [m for a in score.arrangements
                if (m := matching(a, flute_key, fingering)) and (match != "whole" or m["whole_match"])]
        items.append(value)
    return {"items": items, "page": page, "size": size, "total": total, "total_pages": (total+size-1)//size}


def categories(db: Session, user_id: int | None, scope="public", q=None) -> dict:
    counts = store.category_counts(db, scope_owner(scope, user_id), q)
    combinations = {(k, f): count for k, f, count in counts["groups"]}
    groups = [{"flute_key": k, "label": k+"调笛", "score_count": counts["keys"][k],
               "fingerings": [{"code": f, "label": rules.FINGERINGS[f]["label"], "score_count": combinations[(k, f)]}
                              for f in rules.FINGERINGS if (k, f) in combinations]}
              for k in rules.KEYS if k in counts["keys"]]
    result = {"groups": groups, "total_visible_scores": counts["total_visible_scores"],
              "classified_score_count": counts["classified_score_count"]}
    if scope == "mine":
        result.update(pending_score_count=counts["pending_score_count"], review_score_count=counts["review_score_count"])
    return result


def asset_view(asset: ScoreAsset) -> dict:
    return AssetView(id=asset.id, purpose=asset.purpose, arrangement_id=asset.arrangement_id,
        media_type=asset.media_type, size=asset.size, processing_status=asset.processing_status,
        issues=asset.issues, created_at=asset.created_at.replace(tzinfo=timezone.utc).isoformat()).model_dump()
