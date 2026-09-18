from io import BytesIO
from pathlib import Path
from uuid import uuid4
import wave
import pytest
from PIL import Image
from sqlalchemy import select
from app.models.score import Score
from app.models.classification import ScoreAsset
from app.models.user import User
from app.services import score_assets
from classification_tests.test_api import create, manual, section, edit, action


def png():
    buffer = BytesIO()
    Image.new('RGB', (2, 2), 'white').save(buffer, 'PNG')
    return buffer.getvalue()


def wav():
    buffer = BytesIO()
    with wave.open(buffer, 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b'\0' * 320)
    return buffer.getvalue()


def upload(api, sid, tag, content, purpose='score_image', arrangement_id=None, key=None):
    data = {"purpose": purpose}
    if arrangement_id:
        data['arrangement_id'] = str(arrangement_id)
    return api.post(f'/scores/{sid}/assets', data=data, files={'file': ('../../unsafe.html', content, 'text/html')},
        headers={**api.headers_for(), 'If-Match': tag, 'Idempotency-Key': key or str(uuid4())})


def test_asset_private_read_replay_and_detachment(api):
    score, tag = create(api, decision=manual())
    sid = score['id']
    response = upload(api, sid, tag, png(), key='image')
    assert response.status_code == 201, response.text
    asset = response.json()['data']
    assert asset['media_type'] == 'image/png' and asset['processing_status'] == 'stored'
    assert 'storage_key' not in asset and 'path' not in str(asset)
    replay = upload(api, sid, tag, png(), key='image')
    assert replay.json() == response.json() and replay.headers['etag'] == response.headers['etag']
    path = f'/scores/{sid}/assets/{asset["id"]}'
    assert api.get(path).status_code == 404
    assert api.get(path, headers=api.headers_for('other')).status_code == 404
    own = api.get(path, headers=api.headers_for())
    assert own.content == png() and own.headers['cache-control'] == 'private, no-store'
    assert own.headers['content-disposition'].endswith(f'"score-asset-{asset["id"]}.png"')
    published = action(api, sid, response.headers['etag'], 'publish')
    assert api.get(path).status_code == 404  # score publication is not attachment consent
    assert api.get(f'/scores/{sid}').json()['data']['assets'] == []
    deletion = api.delete(path, headers={**api.headers_for(), 'If-Match': published.headers['etag']})
    assert deletion.status_code == 200
    assert api.get(path, headers=api.headers_for()).status_code == 404
    assert len(list(Path(score_assets.CLASSIFICATION_ASSET_DIR).iterdir())) == 1  # retained safely
    assert api.get('/score-categories').json()['data']['classified_score_count'] == 1


def test_machine_notation_is_never_automatically_available(api):
    score, tag = create(api, decision=manual())
    sid, a = score['id'], score['arrangements'][0]
    abc = b'X:1\nT:Test\nM:4/4\nK:C\nCDEF|'
    response = upload(api, sid, tag, abc, 'machine_notation', a['id'])
    assert response.status_code == 201
    asset = response.json()['data']
    capability = api.get(f'/scores/{sid}/arrangements/{a["id"]}/practice-capability', headers=api.headers_for()).json()['data']
    assert capability == {'status': 'unverified', 'available': False, 'notation_asset_id': asset['id'], 'reasons': ['NOTATION_NOT_VERIFIED']}
    bindings = api.put(f'/scores/{sid}/arrangements/{a["id"]}/notation-bindings', json={
        'notation_asset_id': asset['id'], 'bindings': [{'section_id': a['sections'][0]['id'], 'start_measure': 1, 'end_measure': 1, 'part_ref': '1'}]},
        headers={**api.headers_for(), 'If-Match': response.headers['etag']})
    assert bindings.status_code == 409 and bindings.json()['detail']['reason'] == 'NOTATION_NOT_READY'
    assert api.get(f'/scores/{sid}', headers=api.headers_for()).headers['etag'] == response.headers['etag']
    # Deleting an arrangement preserves the asset and detaches its association.
    added = api.post(f'/scores/{sid}/arrangements', json={'label':'alternative', 'coverage':'complete', 'sections':[section()]},
        headers={**api.headers_for(), 'If-Match': response.headers['etag'], 'Idempotency-Key':'add'})
    assert added.status_code == 201
    removed = api.delete(f'/scores/{sid}/arrangements/{a["id"]}?replacement_default_id={added.json()["data"]["id"]}',
        headers={**api.headers_for(), 'If-Match': added.headers['etag']})
    assert removed.status_code == 200, removed.text
    result = api.get(f'/scores/{sid}', headers=api.headers_for()).json()['data']
    assert result['assets'][0]['arrangement_id'] is None and not result['arrangements'][0]['practice_capability']['available']


def test_asset_validation_limits_and_foreign_references(api, monkeypatch):
    score, tag = create(api)
    sid = score['id']
    assert upload(api, sid, tag, b'<html>bad</html>').status_code == 415
    assert upload(api, sid, tag, png(), 'reference_audio').status_code == 415
    assert upload(api, sid, tag, b'not abc', 'machine_notation', score['arrangements'][0]['id']).status_code == 415
    assert upload(api, sid, tag, b'K:C\nC|', 'machine_notation').status_code == 422
    assert upload(api, sid, tag, png(), arrangement_id=987654).status_code == 404
    monkeypatch.setattr(score_assets, 'CLASSIFICATION_MAX_ASSET_SIZE', 10)
    assert upload(api, sid, tag, png()).status_code == 413
    assert api.get(f'/scores/{sid}', headers=api.headers_for()).json()['data']['assets'] == []
    monkeypatch.setattr(score_assets, 'CLASSIFICATION_MAX_ASSET_SIZE', 100000)
    response = upload(api, sid, tag, wav(), 'reference_audio')
    assert response.status_code == 201 and response.json()['data']['media_type'] == 'audio/wav'


def test_file_write_failure_rolls_back(api, monkeypatch):
    score, tag = create(api)
    original = score_assets.store.flush
    def fail(db):
        raise OSError('simulated storage/commit failure')
    monkeypatch.setattr(score_assets.store, 'flush', fail)
    with pytest.raises(OSError):
        upload(api, score['id'], tag, png())
    monkeypatch.setattr(score_assets.store, 'flush', original)
    response = api.get(f'/scores/{score["id"]}', headers=api.headers_for())
    assert response.headers['etag'] == tag and response.json()['data']['assets'] == []
    assert (Path(score_assets.CLASSIFICATION_ASSET_DIR) / 'recycle').is_dir()


def test_safe_asset_copy_and_source_revocation(api):
    score, tag = create(api, decision=manual())
    response = upload(api, score['id'], tag, png())
    asset_id = response.json()['data']['id']
    # An independently verified consent record; no public grant is inferred by API.
    with api.factory() as db:
        asset = db.get(ScoreAsset, asset_id)
        asset.public_allowed = asset.copy_allowed = True
        db.commit()
    published = action(api, score['id'], response.headers['etag'], 'publish')
    assert api.get(f'/scores/{score["id"]}/assets/{asset_id}').status_code == 200
    copied = api.post(f'/scores/{score["id"]}/copies', json={}, headers={**api.headers_for('other'), 'Idempotency-Key':'copy'})
    assert copied.status_code == 201
    copy = copied.json()['data']
    assert len(copy['assets']) == 1
    action(api, score['id'], published.headers['etag'], 'unpublish')
    path = f'/scores/{copy["id"]}/assets/{copy["assets"][0]["id"]}'
    assert api.get(path, headers=api.headers_for('other')).content == png()
    assert api.get(path).status_code == 404


def test_playlist_cannot_reveal_revoked_score(api):
    score, tag = create(api, decision=manual())
    headers = api.headers_for('other')
    playlist = api.post('/playlists/', json={'name':'练习'}, headers=headers)
    assert playlist.status_code == 200
    pid = playlist.json()['id']
    assert api.post(f'/playlists/{pid}/items?score_id={score["id"]}', headers=headers).status_code == 404
    published = action(api, score['id'], tag, 'publish')
    added = api.post(f'/playlists/{pid}/items?score_id={score["id"]}', headers=headers)
    assert added.status_code == 200, added.text
    assert added.json()['score']['title'] == score['title']
    assert 'audio_path' not in added.json()['score']
    assert action(api, score['id'], published.headers['etag'], 'unpublish').status_code == 200
    playlists = api.get('/playlists/', headers=headers)
    assert playlists.status_code == 200
    assert playlists.json()[0]['items'][0]['score'] is None


def test_static_bypass_and_candidate_token_auth_rejected(api, tmp_path, monkeypatch):
    from app.api.endpoints import private_uploads
    root = tmp_path / 'uploads'
    root.mkdir()
    (root / 'private.png').write_bytes(png())
    monkeypatch.setattr(private_uploads, 'UPLOAD_DIR', str(root))
    score, tag = create(api)
    with api.factory() as db:
        db.get(Score, score['id']).image_path = str(root / 'private.png')
        db.add(User(username='1', hashed_password='unused', role='user'))
        db.commit()
    assert api.get('/uploads/private.png').status_code == 401
    assert api.get('/uploads/private.png', headers=api.headers_for('other')).status_code == 404
    assert api.get('/uploads/private.png', headers=api.headers_for()).content == png()
    token = api.post('/flute-key-candidates', json={'original_key':'D','fingering':{'code':'closed_2'}}, headers=api.headers_for()).json()['data']['candidate_token']
    assert api.get('/scores/?scope=mine', headers={'Authorization':'Bearer '+token}).status_code == 401


def test_legacy_assets_are_discoverable_without_storage_path_leaks(api, tmp_path, monkeypatch):
    from datetime import datetime
    root = tmp_path / 'uploads'
    root.mkdir()
    (root / 'legacy.png').write_bytes(png())
    monkeypatch.setattr(score_assets, 'UPLOAD_DIR', str(root))
    score, tag = create(api)
    with api.factory() as db:
        db.add(ScoreAsset(score_id=score['id'], purpose='score_image', storage_key='legacy-image', legacy_path=str(root/'legacy.png'),
            media_type='application/octet-stream', size=None, processing_status='stored', issues=[{'reason':'LEGACY_CONTENT_UNVERIFIED'}],
            public_allowed=False, copy_allowed=False, created_at=datetime.utcnow()))
        db.commit()
    detail = api.get(f'/scores/{score["id"]}', headers=api.headers_for()).json()['data']
    asset = detail['assets'][0]
    assert 'legacy_path' not in asset and str(root) not in str(detail)
    response = api.get(f'/scores/{score["id"]}/assets/{asset["id"]}', headers=api.headers_for())
    assert response.status_code == 200 and response.content == png()
    assert response.headers['content-type'] == 'application/octet-stream'
    with api.factory() as db:
        db.get(ScoreAsset, asset['id']).legacy_path = str(tmp_path / 'outside')
        db.commit()
    (tmp_path / 'outside').write_text('private')
    assert api.get(f'/scores/{score["id"]}/assets/{asset["id"]}', headers=api.headers_for()).status_code == 404
