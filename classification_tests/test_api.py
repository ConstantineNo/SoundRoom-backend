from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from jose import jwt
from sqlalchemy import select, func
from app.models.score import Score
from app.models.classification import Arrangement, Section, IdempotencyRecord
from app.services import flute_candidates as rules
from app.core.config import SECRET_KEY, ALGORITHM


def create(api, decision=None, name="owner", **fields):
    data = {"title": "春江", "original_key": "D", "fingering": {"code": "closed_2"}, **fields}
    if decision:
        data["classification_decision"] = decision
    response = api.post("/scores/", json=data, headers={**api.headers_for(name), "Idempotency-Key": str(uuid4())})
    assert response.status_code == 201, response.text
    return response.json()["data"], response.headers["etag"]


def manual(key="A"):
    return {"method": "manual", "flute_key": key}


def section(fingering="closed_2", flute="A", **fields):
    data = {"location_label": "段落", "fingering": {"code": fingering}, **fields}
    if flute:
        data["classification_decision"] = manual(flute)
    return data


def edit(api, score, tag, sections, **fields):
    a = score["arrangements"][0]
    response = api.put(f'/scores/{score["id"]}/arrangements/{a["id"]}',
        json={"label": "方案", "coverage": "complete", "sections": sections, **fields},
        headers={**api.headers_for(), "If-Match": tag})
    assert response.status_code == 200, response.text
    return response.json()["data"], response.headers["etag"]


def action(api, score_id, tag, operation, name="owner"):
    return api.post(f"/scores/{score_id}/{operation}", headers={**api.headers_for(name), "If-Match": tag})


def test_quick_create_and_protocol(api):
    score, tag = create(api, title="  春江  ", notes=None)
    assert score["title"] == "春江"
    assert score["visibility"] == "private" and score["assets"] == []
    a = score["arrangements"][0]
    assert a["is_default"] and a["coverage"] == "complete"
    assert a["sections"][0]["location_label"] == "全曲"
    assert a["sections"][0]["classification_status"] == "pending"
    assert a["practice_capability"]["status"] == "not_provided"
    assert a["requires_flute_switch"] is None
    detail = api.get(f'/scores/{score["id"]}', headers=api.headers_for())
    assert detail.status_code == 200 and detail.headers["etag"] == tag
    assert "matched_arrangements" not in detail.json()["data"]
    pending = api.get('/scores/?scope=mine&classification=pending', headers=api.headers_for()).json()["data"]
    assert pending["total"] == 1
    assert api.get('/scores/?scope=mine').status_code == 401
    assert api.get('/scores/').json()["data"]["total"] == 0


@pytest.mark.parametrize("code,expected", [("closed_1", "G"), ("closed_2", "A"), ("closed_3", "B"),
    ("closed_4", "C"), ("closed_5", "D"), ("closed_6", "E"), ("closed_b7", "F"), ("closed_7", "F#")])
def test_documented_d_row(api, code, expected):
    response = api.post('/flute-key-candidates', json={"original_key": "D", "fingering": {"code": code}}, headers=api.headers_for())
    assert response.status_code == 200
    result = response.json()["data"]
    assert result["outcome"] == "single" and result["candidates"][0]["flute_key"] == expected
    assert not result["range_checked"] and result["candidate_token"] and result["expires_at"].endswith("+00:00")


@pytest.mark.parametrize("key,expected", [("1=A", "E"), ("6=A", "G"), ("1=D", "A"), ("Db", "G#"), ("C#", "G#"), ("F♯", "C#")])
def test_notation_and_enharmonics(api, key, expected):
    result = api.post('/flute-key-candidates', json={"original_key": key, "fingering": {"raw": "全按做2"}}, headers=api.headers_for()).json()["data"]
    assert result["candidates"][0]["flute_key"] == expected


@pytest.mark.parametrize("extra,outcome", [({"original_key": "A小调"}, "missing_input"),
    ({"key_basis": "local"}, "missing_input"), ({"instrument_profile": "seven_hole"}, "unsupported"),
    ({"fingering": {"raw": "筒音作降3"}}, "unsupported")])
def test_no_invented_inference(api, extra, outcome):
    result = api.post('/flute-key-candidates', json={"original_key": "D", "fingering": {"code": "closed_2"}, **extra}, headers=api.headers_for()).json()["data"]
    assert result["outcome"] == outcome and not result["candidates"] and result["candidate_token"] is None


def test_candidate_confirmation_security_and_atomic_failure(api):
    inputs = {"original_key": "D", "fingering": {"raw": "全按作2"}}
    candidate = api.post('/flute-key-candidates', json=inputs, headers=api.headers_for()).json()["data"]
    decision = {"method": "candidate", "flute_key": "A", "candidate_token": candidate["candidate_token"]}
    score, _ = create(api, decision=decision)
    s = score["arrangements"][0]["sections"][0]
    assert s["classification_status"] == "confirmed" and s["flute_key"] == "A"
    cases = [("owner", {"original_key": "E"}, decision), ("other", {}, decision),
             ("owner", {}, {**decision, "flute_key": "D"}), ("owner", {}, {**decision, "candidate_token": "broken"})]
    decoded = jwt.decode(candidate["candidate_token"], SECRET_KEY, algorithms=[ALGORITHM])
    decoded["exp"] = datetime.now(timezone.utc) - timedelta(seconds=5)
    cases.append(("owner", {}, {**decision, "candidate_token": jwt.encode(decoded, SECRET_KEY, algorithm=ALGORITHM)}))
    for name, extra, selected in cases:
        response = api.post('/scores/', json={"title": "invalid", **inputs, **extra, "classification_decision": selected},
            headers={**api.headers_for(name), "Idempotency-Key": str(uuid4())})
        assert response.status_code == 409 and response.json()["detail"]["reason"] == "CANDIDATE_STALE"
    with api.factory() as db:
        assert db.scalar(select(func.count()).select_from(Score)) == 1
        assert db.scalar(select(func.count()).select_from(Arrangement)) == 1
        assert db.scalar(select(func.count()).select_from(Section)) == 1


def test_manual_unknown_and_mismatch(api):
    score, _ = create(api, decision=manual("G"))
    assert score["arrangements"][0]["sections"][0]["classification_evidence"]["warnings"] == [{"reason": "KEY_RELATION_MISMATCH"}]
    score, _ = create(api, decision=manual(), original_key="未注明", instrument_profile="custom")
    assert score["arrangements"][0]["sections"][0]["classification_evidence"]["warnings"] == [{"reason": "RELATION_NOT_CHECKED"}]
    score, _ = create(api, fingering={"raw": "未知指法"})
    assert score["arrangements"][0]["sections"][0]["fingering"]["raw"] == "未知指法"
    result = api.post('/scores/', json={"title": "x", "original_key": "D", "fingering": {"raw": "未知"}, "classification_decision": manual()},
        headers={**api.headers_for(), "Idempotency-Key": "unknown"})
    assert result.status_code == 422


def test_only_dependent_sections_invalidated(api):
    score, tag = create(api, decision=manual())
    a, tag = edit(api, score, tag, [section(), section(local_key="A", key_basis="local"),
                                  section(performance_key="D", key_basis="performance")])
    response = api.patch(f'/scores/{score["id"]}', json={"original_key": "E"}, headers={**api.headers_for(), "If-Match": tag})
    assert response.status_code == 200
    sections = response.json()["data"]["arrangements"][0]["sections"]
    assert [s["classification_status"] for s in sections] == ["needs_review", "confirmed", "confirmed"]
    assert sections[0]["flute_key"] is None and sections[0]["classification_evidence"]["previous_flute_key"] == "A"
    tag = response.headers["etag"]
    change = api.patch(f'/scores/{score["id"]}', json={"title": "new", "notes": None, "tags": []}, headers={**api.headers_for(), "If-Match": tag})
    assert change.json()["data"]["arrangements"][0]["sections"] == sections


def test_order_replacement_and_dependency_tracking(api):
    score, tag = create(api, decision=manual())
    a, tag = edit(api, score, tag, [section(), section("closed_5", "D"), section()])
    assert [s["fingering"]["code"] for s in a["sections"]] == ["closed_2", "closed_5", "closed_2"]
    assert a["requires_flute_switch"] and a["requires_fingering_switch"]
    values = [section(flute=None, id=s["id"]) for s in (a["sections"][2], a["sections"][0])]
    values[0]["instrument_profile"] = "custom"
    updated, tag = edit(api, score, tag, values)
    assert [s["id"] for s in updated["sections"]] == [a["sections"][2]["id"], a["sections"][0]["id"]]
    assert [s["classification_status"] for s in updated["sections"]] == ["needs_review", "confirmed"]
    assert updated["requires_flute_switch"] is None
    assert api.get('/score-categories?scope=mine', headers=api.headers_for()).json()["data"]["groups"][0]["score_count"] == 1
    with api.factory() as db:
        assert db.scalar(select(func.count()).select_from(Section)) == 2


def test_categories_same_section_whole_match_and_paging(api):
    score, tag = create(api, decision=manual())
    _, tag = edit(api, score, tag, [section(), section("closed_5", "D"), section()])
    create(api, decision=manual(), title="second")
    query = '/scores/?scope=mine&flute_key=A&fingering=closed_2'
    found = api.get(query, headers=api.headers_for()).json()["data"]
    assert found["total"] == 2
    partial = next(s for s in found["items"] if s["id"] == score["id"])["matched_arrangements"][0]
    assert len(partial["section_ids"]) == 2 and not partial["whole_match"]
    assert len(partial["required_combinations"]) == 2
    assert api.get(query + '&match=whole', headers=api.headers_for()).json()["data"]["total"] == 1
    assert api.get('/scores/?scope=mine&flute_key=A&fingering=closed_5', headers=api.headers_for()).json()["data"]["total"] == 0
    pages = [api.get(query + f'&size=1&page={i}', headers=api.headers_for()).json()["data"] for i in (1, 2)]
    assert pages[0]["items"][0]["id"] != pages[1]["items"][0]["id"]
    groups = api.get('/score-categories?scope=mine', headers=api.headers_for()).json()["data"]
    assert groups["total_visible_scores"] == 2 and groups["classified_score_count"] == 2
    assert {g["flute_key"]: g["score_count"] for g in groups["groups"]} == {"D": 1, "A": 2}
    # Unknown scope is never a whole match even when every registered section matches.
    _, tag = edit(api, score, tag, [section()], coverage="unknown")
    assert api.get(query + '&match=whole', headers=api.headers_for()).json()["data"]["total"] == 1


def test_alternative_defaults_removal_and_retry(api):
    score, tag = create(api, decision=manual())
    sid, aid = score["id"], score["arrangements"][0]["id"]
    data = {"label": "替代", "coverage": "complete", "is_default": True, "sections": [section("closed_5", "D")]}
    headers = {**api.headers_for(), "If-Match": tag, "Idempotency-Key": "add"}
    result = api.post(f'/scores/{sid}/arrangements', json=data, headers=headers)
    assert result.status_code == 201
    retry = api.post(f'/scores/{sid}/arrangements', json=data, headers=headers)
    assert retry.status_code == 201 and retry.json() == result.json() and retry.headers["etag"] == result.headers["etag"]
    new_id = result.json()["data"]["id"]
    assert not result.json()["data"]["requires_flute_switch"]
    detail = api.get(f'/scores/{sid}', headers=api.headers_for()).json()["data"]
    assert [a["is_default"] for a in detail["arrangements"]] == [False, True]
    headers["If-Match"] = result.headers["etag"]
    deletion = api.delete(f'/scores/{sid}/arrangements/{new_id}', headers=headers)
    assert deletion.status_code == 409 and deletion.json()["detail"]["reason"] == "DEFAULT_REPLACEMENT_REQUIRED"
    deletion = api.delete(f'/scores/{sid}/arrangements/{new_id}?replacement_default_id={aid}', headers=headers)
    assert deletion.status_code == 200
    headers["If-Match"] = deletion.headers["etag"]
    assert api.delete(f'/scores/{sid}/arrangements/{aid}', headers=headers).json()["detail"]["reason"] == "LAST_ARRANGEMENT"
    assert [g["flute_key"] for g in api.get('/score-categories?scope=mine', headers=api.headers_for()).json()["data"]["groups"]] == ["A"]


def test_privacy_sharing_copy_and_nested_authorization(api):
    score, tag = create(api, decision=manual(), notes="公开演奏备注")
    sid, aid = score["id"], score["arrangements"][0]["id"]
    for name in (None, "other", "admin"):
        headers = api.headers_for(name) if name else {}
        assert api.get(f'/scores/{sid}', headers=headers).status_code == 404
        assert api.get(f'/scores/{sid}/arrangements/{aid}/practice-capability', headers=headers).status_code == 404
        if name:
            assert api.patch(f'/scores/{sid}', json={"title": "steal"}, headers={**headers, "If-Match": tag}).status_code == 404
    published = action(api, sid, tag, "publish")
    assert published.status_code == 200
    public = api.get(f'/scores/{sid}').json()["data"]
    assert "classification_evidence" not in public["arrangements"][0]["sections"][0]
    assert "candidate_token" not in str(public) and "audio_path" not in public
    assert api.get('/score-categories').json()["data"]["classified_score_count"] == 1
    assert "pending_score_count" not in api.get('/score-categories').json()["data"]
    assert action(api, sid, published.headers["etag"], "unpublish", "other").status_code == 403
    copied = api.post(f'/scores/{sid}/copies', json={}, headers={**api.headers_for("other"), "Idempotency-Key": "copy"})
    assert copied.status_code == 201
    copy = copied.json()["data"]
    assert copy["id"] != sid and copy["owner"]["id"] == 2 and copy["visibility"] == "private"
    assert copy["arrangements"][0]["sections"][0]["classification_status"] == "confirmed"
    assert copy["arrangements"][0]["id"] != aid
    assert not copy["arrangements"][0]["practice_capability"]["available"]
    assert api.get(f'/scores/{sid}/arrangements/{copy["arrangements"][0]["id"]}/practice-capability').status_code == 404
    assert action(api, sid, published.headers["etag"], "unpublish").status_code == 200
    assert api.get(f'/scores/{sid}').status_code == 404
    assert api.get(f'/scores/{copy["id"]}', headers=api.headers_for("other")).status_code == 200
    assert api.post(f'/scores/{sid}/copies', json={}, headers={**api.headers_for("other"), "Idempotency-Key": "copy"}).status_code == 404


def test_if_match_and_idempotency_concurrent(api):
    data = {"title": "并发", "original_key": "D", "fingering": {"code": "closed_2"}}
    headers = {**api.headers_for(), "Idempotency-Key": "concurrent"}
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: api.post('/scores/', json=data, headers=headers), range(4)))
    assert all(r.status_code == 201 for r in responses), [r.text for r in responses]
    assert len({r.json()["data"]["id"] for r in responses}) == 1
    assert api.post('/scores/', json={**data, "title": "changed"}, headers=headers).status_code == 409
    sid, tag = responses[0].json()["data"]["id"], responses[0].headers["etag"]
    assert api.patch(f'/scores/{sid}', json={"title": "new"}, headers=api.headers_for()).status_code == 428
    with ThreadPoolExecutor(max_workers=2) as pool:
        writes = list(pool.map(lambda i: api.patch(f'/scores/{sid}', json={"title": f"new{i}"},
            headers={**api.headers_for(), "If-Match": tag}), range(2)))
    assert sorted(r.status_code for r in writes) == [200, 412]
    assert api.post('/scores/', json=data, headers=headers).json() == responses[0].json()


@pytest.mark.parametrize("extra", [{"owner_id": 2}, {"classification_status": "confirmed"}, {"practice_available": True},
    {"title": " "}, {"title": "x"*101}, {"fingering": {"code": "closed_8"}}, {"fingering": {"code": "closed_2", "raw": "全按作2"}},
    {"classification_decision": {"method": "manual", "flute_key": "Db"}}])
def test_invalid_creation(api, extra):
    response = api.post('/scores/', json={"title": "曲目", "original_key": "D", "fingering": {"code": "closed_2"}, **extra},
        headers={**api.headers_for(), "Idempotency-Key": "invalid"})
    assert response.status_code == 422
    assert response.json()["code"] == 20001 and response.json()["detail"]["reason"] == "INVALID_INPUT"


@pytest.mark.parametrize("query", ["skip=0&limit=1", "fingering=closed_2", "match=whole&flute_key=A", "classification=pending", "scope=wrong", "page=0", "size=101"])
def test_invalid_queries(api, query):
    assert api.get('/scores/?' + query).status_code == 422


def test_atomic_nested_updates_and_legacy_guard(api):
    score, tag = create(api, decision=manual())
    other, _ = create(api, decision=manual())
    sid, aid = score["id"], score["arrangements"][0]["id"]
    section_id = score["arrangements"][0]["sections"][0]["id"]
    for sections, expected in [([], 422), ([section(id=section_id), section(id=section_id)], 422),
        ([section(id=other["arrangements"][0]["sections"][0]["id"])], 404)]:
        r = api.put(f'/scores/{sid}/arrangements/{aid}', json={"label": "bad", "coverage": "complete", "sections": sections},
            headers={**api.headers_for(), "If-Match": tag})
        assert r.status_code == expected
        assert api.get(f'/scores/{sid}', headers=api.headers_for()).headers["etag"] == tag
    updated = api.put(f'/scores/{sid}', json={"flute_key": "D", "fingering": "全按作5"}, headers={**api.headers_for(), "If-Match": tag})
    assert updated.status_code == 200
    s = updated.json()["data"]["arrangements"][0]["sections"][0]
    assert s["flute_key"] == "D" and s["classification_evidence"]["method"] == "manual"
    _, tag = edit(api, score, updated.headers["etag"], [section(), section()])
    assert api.put(f'/scores/{sid}', json={"flute_key": "G"}, headers={**api.headers_for(), "If-Match": tag}).json()["detail"]["reason"] == "LEGACY_AMBIGUOUS"
    assert api.put(f'/scores/{sid}/abc', json={"abc_content": "X:1\nK:C\nC D E F|"}, headers=api.headers_for("other")).status_code == 404
    assert api.delete(f'/scores/{sid}', headers=api.headers_for()).status_code == 409


def test_options_and_tags_search(api):
    dictionary = api.get('/score-classification-options').json()["data"]
    assert len(dictionary["flute_keys"]) == 12 and len(dictionary["fingerings"]) == 8
    assert "全按作2" in next(f for f in dictionary["fingerings"] if f["code"] == "closed_2")["aliases"]
    create(api, tags=["江南"], notes="秘密")
    assert api.get('/scores/?scope=mine&q=江南', headers=api.headers_for()).json()["data"]["total"] == 1
    assert api.get('/score-categories?scope=mine&q=秘密', headers=api.headers_for()).json()["data"]["total_visible_scores"] == 0


def test_classification_intersection_and_all_arrangements(api):
    score, tag = create(api, decision=manual(), tags=['100% literal'])
    response = api.post(f'/scores/{score["id"]}/arrangements', json={
        'label':'unfinished', 'coverage':'complete', 'sections':[section(flute=None)]},
        headers={**api.headers_for(), 'If-Match':tag, 'Idempotency-Key':'pending'})
    assert response.status_code == 201
    query = '/scores/?scope=mine&flute_key=A&fingering=closed_2'
    assert api.get(query+'&classification=confirmed', headers=api.headers_for()).json()['data']['total'] == 0
    assert api.get(query+'&classification=pending', headers=api.headers_for()).json()['data']['total'] == 1
    assert api.get(query+'&match=whole', headers=api.headers_for()).json()['data']['total'] == 1
    assert api.get('/scores/?scope=mine&q=%25', headers=api.headers_for()).json()['data']['total'] == 1
    assert api.get('/scores/?scope=mine&q=_', headers=api.headers_for()).json()['data']['total'] == 0
    grouped = api.get('/score-categories?scope=mine', headers=api.headers_for()).json()['data']
    assert grouped['pending_score_count'] == grouped['classified_score_count'] == 1


def test_local_candidate_depends_only_on_selected_key(api):
    data = {'original_key':'D', 'local_key':'1=A', 'key_basis':'local', 'fingering':{'code':'closed_5'}}
    inferred = api.post('/flute-key-candidates', json=data, headers=api.headers_for()).json()['data']
    assert inferred['candidates'][0]['flute_key'] == 'A'
    score, tag = create(api, original_key='E')
    arrangement, tag = edit(api, score, tag, [section('closed_5', None, local_key='1=A', key_basis='local',
        classification_decision={'method':'candidate', 'flute_key':'A', 'candidate_token':inferred['candidate_token']})])
    assert arrangement['sections'][0]['classification_status'] == 'confirmed'
    section_id = arrangement['sections'][0]['id']
    arrangement, tag = edit(api, score, tag, [section('closed_5', None, id=section_id, local_key='1=D', key_basis='local')])
    assert arrangement['sections'][0]['classification_status'] == 'needs_review'
    assert arrangement['sections'][0]['classification_evidence']['previous_flute_key'] == 'A'


def test_same_flute_two_fingerings_counts_once_at_both_levels(api):
    score, tag = create(api, decision=manual())
    a, tag = edit(api, score, tag, [section(), section('closed_5', 'A', local_key='A', key_basis='local'), section()])
    assert not a['requires_flute_switch'] and a['requires_fingering_switch']
    groups = api.get('/score-categories?scope=mine', headers=api.headers_for()).json()['data']['groups']
    assert len(groups) == 1 and groups[0]['score_count'] == 1
    assert [f['score_count'] for f in groups[0]['fingerings']] == [1, 1]


def test_idempotency_expiry_and_scope(api):
    body = {'title':'retry', 'original_key':'D', 'fingering':{'code':'closed_2'}}
    headers = {**api.headers_for(), 'Idempotency-Key':'same'}
    first = api.post('/scores/', json=body, headers=headers)
    assert first.status_code == 201
    other = api.post('/scores/', json=body, headers={**api.headers_for('other'), 'Idempotency-Key':'same'})
    assert other.status_code == 201 and other.json()['data']['id'] != first.json()['data']['id']
    with api.factory() as db:
        record = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.user_id == 1))
        record.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
    expired = api.post('/scores/', json=body, headers=headers)
    assert expired.status_code == 201 and expired.json()['data']['id'] != first.json()['data']['id']
    assert api.post('/scores/', json=body, headers=api.headers_for()).status_code == 422


def test_legacy_abc_unique_arrangement_and_key_invalidation(api):
    score, tag = create(api, decision=manual())
    sid = score['id']
    updated = api.put(f'/scores/{sid}/abc', json={'abc_content':'X:1\nT:Test\nM:4/4\nK:C\nC D E F|'},
        headers={**api.headers_for(), 'If-Match':tag})
    assert updated.status_code == 200, updated.text
    assert not updated.json()['data']['arrangements'][0]['practice_capability']['available']
    with api.factory() as db:
        saved = db.get(Score, sid)
        assert saved.abc_source and saved.structured_data
    patched = api.put(f'/scores/{sid}', json={'song_key':'E'}, headers={**api.headers_for(), 'If-Match':updated.headers['etag']})
    assert patched.status_code == 200
    assert patched.json()['data']['arrangements'][0]['sections'][0]['classification_status'] == 'needs_review'
    second = api.post(f'/scores/{sid}/arrangements', json={'label':'second','coverage':'complete','sections':[section()]},
        headers={**api.headers_for(), 'If-Match':patched.headers['etag'], 'Idempotency-Key':'second'})
    conflict = api.put(f'/scores/{sid}/abc', json={'abc_content':'X:1\nK:C\nC|'}, headers={**api.headers_for(), 'If-Match':second.headers['etag']})
    assert conflict.status_code == 409 and conflict.json()['detail']['reason'] == 'LEGACY_AMBIGUOUS'
