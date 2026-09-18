"""Edition contract: partial dates, merge semantics, privacy and upgrade compatibility."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4
import pytest
from sqlalchemy import func, select
from app.models.score import Score
from app.models.classification import IdempotencyRecord
from classification_tests.test_api import create, manual, edit, section, action

EMPTY = dict.fromkeys(('label', 'original_artist', 'performer', 'album', 'release_date'))
FULL = {'label':'现场版', 'original_artist':'原唱甲、原唱乙', 'performer':'表演者丙', 'album':'出版物丁', 'release_date':'2020-02'}


def patch(api, sid, tag, body, expected=200, user='owner'):
    response = api.patch(f'/scores/{sid}', json=body, headers={**api.headers_for(user), 'If-Match':tag})
    assert response.status_code == expected, response.text
    return response


@pytest.mark.parametrize('extra', [{}, {'edition':None}, {'edition':{}}, {'edition':EMPTY}])
def test_empty_create_legacy_compatibility_and_output(api, extra):
    score, tag = create(api, decision=manual(), **extra)
    assert score['edition'] == EMPTY
    sid = score['id']
    for response in [api.get(f'/scores/{sid}',headers=api.headers_for()), action(api,sid,tag,'publish')]:
        assert response.status_code == 200 and response.json()['data']['edition'] == EMPTY
    assert api.get('/scores/').json()['data']['items'][0]['edition'] == EMPTY


@pytest.mark.parametrize('field', list(EMPTY))
def test_each_optional_field_roundtrips_without_fabrication(api, field):
    value = '2020' if field == 'release_date' else ' 单项文本 '
    score, _ = create(api, edition={field:value})
    assert score['edition'] == {**EMPTY,field:value.strip()}


def test_normalization_and_plain_text(api):
    score, _ = create(api, edition={'label':'  现场版  ','original_artist':'甲, 乙','performer':'\n\t ',
        'album':' <b>原样文字</b> ', 'release_date':' 2020 '})
    assert score['edition'] == {'label':'现场版','original_artist':'甲, 乙','performer':None,
        'album':'<b>原样文字</b>','release_date':'2020'}


@pytest.mark.parametrize('value', ['0001','9999','0001-01','2020','2020-02','2020-02-29','2000-02-29','2400-02-29',
                                  '2024-04-30','9999-12-31','2099-12-31',None,'   '])
def test_partial_date_validity_and_precision(api, value):
    score, _ = create(api, edition={'release_date':value})
    expected = value.strip() or None if isinstance(value,str) else None
    assert score['edition']['release_date'] == expected


@pytest.mark.parametrize('value', ['0000','10000','2020-00','2020-13','2020-2','2020-02-30','2023-02-29','1900-02-29',
    '2024-04-31','2020-01-00','2020-1-01','20','2020/01/01','２０２０','2020-01-01T00:00:00Z',2020,True,{}])
def test_invalid_dates_reject_with_exact_field_path(api, value):
    body = {'title':'日期测试','original_key':'D','fingering':{'code':'closed_2'},'edition':{'release_date':value}}
    response = api.post('/scores/',json=body,headers={**api.headers_for(),'Idempotency-Key':str(uuid4())})
    assert response.status_code == 422
    assert response.json()['detail']['reason'] == 'INVALID_INPUT'
    assert any(e['path']=='body.edition.release_date' for e in response.json()['detail']['field_errors'])
    with api.factory() as db:
        assert db.scalar(select(func.count()).select_from(Score)) == 0


@pytest.mark.parametrize('field,limit', [('label',100),('original_artist',200),('performer',200),('album',200)])
def test_trimmed_text_lengths(api, field, limit):
    score,tag = create(api, edition={field:' '+('字'*limit)+' '})
    assert score['edition'][field] == '字'*limit
    rejected = patch(api,score['id'],tag,{'edition':{field:'字'*(limit+1)}},422)
    assert rejected.json()['detail']['field_errors'][0]['path'] == 'body.edition.'+field
    assert api.get(f'/scores/{score["id"]}',headers=api.headers_for()).headers['etag'] == tag


def test_patch_merge_clear_empty_and_no_inference_side_effects(api, monkeypatch):
    score,tag = create(api,decision=manual(),edition=FULL)
    sid = score['id']
    original_arrangements = deepcopy(score['arrangements'])
    from app.services import flute_candidates
    def forbidden(*args,**kwargs):
        raise AssertionError('edition edit must not infer or parse notation')
    monkeypatch.setattr(flute_candidates,'infer',forbidden)
    response = patch(api,sid,tag,{'edition':{'album':' 新专辑 '}})
    assert response.headers['etag'] != tag
    assert response.json()['data']['edition'] == {**FULL,'album':'新专辑'}
    assert response.json()['data']['arrangements'] == original_arrangements
    tag = response.headers['etag']
    response = patch(api,sid,tag,{'title':'改名'})
    assert response.json()['data']['edition']['original_artist'] == FULL['original_artist']
    tag = response.headers['etag']
    response = patch(api,sid,tag,{'edition':{'release_date':None}})
    assert response.json()['data']['edition'] == {**FULL,'album':'新专辑','release_date':None}
    tag = response.headers['etag']
    patch(api,sid,tag,{'edition':{}},422)
    response = patch(api,sid,tag,{'edition':{},'notes':None})
    assert response.json()['data']['edition']['album'] == '新专辑'
    response = patch(api,sid,response.headers['etag'],{'edition':None})
    assert response.json()['data']['edition'] == EMPTY
    assert response.json()['data']['arrangements'] == original_arrangements


def test_edition_plus_original_key_and_legacy_put(api):
    score,tag = create(api,decision=manual(),edition=FULL)
    a,tag = edit(api,score,tag,[section(),section(local_key='D',key_basis='local')])
    response = patch(api,score['id'],tag,{'original_key':'E','edition':{'label':'重录版'}})
    assert [s['classification_status'] for s in response.json()['data']['arrangements'][0]['sections']] == ['needs_review','confirmed']
    assert response.json()['data']['edition'] == {**FULL,'label':'重录版'}
    legacy = api.put(f'/scores/{score["id"]}',json={'title':'旧客户端改标题'},headers={**api.headers_for(),'If-Match':response.headers['etag']})
    assert legacy.status_code == 200
    assert legacy.json()['data']['edition'] == response.json()['data']['edition']
    rejected = api.put(f'/scores/{score["id"]}',json={'edition':None},headers={**api.headers_for(),'If-Match':legacy.headers['etag']})
    assert rejected.status_code == 422


def test_edition_permissions_copy_and_visibility(api):
    score,tag = create(api,decision=manual(),edition=FULL)
    sid = score['id']
    patch(api,sid,tag,{'edition':{'performer':'越权'}},404,'other')
    patch(api,sid,tag,{'edition':{'performer':'越权'}},404,'admin')
    published = action(api,sid,tag,'publish')
    assert published.status_code == 200 and published.json()['data']['edition'] == FULL
    assert api.get(f'/scores/{sid}').json()['data']['edition'] == FULL
    patch(api,sid,published.headers['etag'],{'edition':None},403,'other')
    copied = api.post(f'/scores/{sid}/copies',json={},headers={**api.headers_for('other'),'Idempotency-Key':'copy-edition'})
    assert copied.status_code == 201
    copy = copied.json()['data']
    assert copy['edition'] == FULL and copy['visibility'] == 'private'
    changed = patch(api,copy['id'],copied.headers['etag'],{'edition':{'performer':'独立副本'}},user='other')
    assert changed.json()['data']['edition']['performer'] == '独立副本'
    assert api.get(f'/scores/{sid}').json()['data']['edition'] == FULL
    unpublished = action(api,sid,published.headers['etag'],'unpublish')
    assert unpublished.json()['data']['edition'] == FULL
    assert api.get(f'/scores/{sid}').status_code == 404
    assert api.get(f'/scores/{copy["id"]}',headers=api.headers_for('other')).json()['data']['edition']['performer'] == '独立副本'


def test_etag_concurrent_metadata_writes(api):
    score,tag = create(api,edition=FULL)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda name: api.patch(f'/scores/{score["id"]}',json={'edition':{'album':name}},
            headers={**api.headers_for(),'If-Match':tag}), ['甲','乙']))
    assert sorted(r.status_code for r in responses) == [200,412]
    response = api.patch(f'/scores/{score["id"]}',json={'edition':None},headers=api.headers_for())
    assert response.status_code == 428


@pytest.mark.parametrize('field,query', [('label','Demo'),('original_artist','原唱'),('performer','演奏者'),('album','100%_专辑')])
def test_search_shared_filters_deduplication_and_privacy(api,field,query):
    for label in ['甲','乙']:
        score,tag = create(api,title='同名曲目',decision=manual(),edition={'label':label,field:query})
        edit(api,score,tag,[section(),section()])
    create(api,title='同名曲目',decision=manual(),edition={field:query},name='other')
    params={'scope':'mine','q':'  '+query.lower()+'  '}
    listed = api.get('/scores/',params={**params,'size':1},headers=api.headers_for()).json()['data']
    counts = api.get('/score-categories',params=params,headers=api.headers_for()).json()['data']
    assert listed['total'] == counts['total_visible_scores'] == counts['classified_score_count'] == 2
    assert listed['total_pages'] == 2 and counts['groups'][0]['score_count'] == 2
    second = api.get('/scores/',params={**params,'size':1,'page':2},headers=api.headers_for()).json()['data']['items'][0]
    assert second['id'] != listed['items'][0]['id']
    assert api.get('/scores/',params={'q':query}).json()['data']['total'] == 0
    assert api.get('/score-categories',params={'q':query}).json()['data']['total_visible_scores'] == 0
    assert api.get('/scores/',params={'scope':'mine','q':'   '},headers=api.headers_for()).json()['data']['total'] == 2
    if field == 'album':
        assert api.get('/scores/',params={'scope':'mine','q':'100X_专辑'},headers=api.headers_for()).json()['data']['total'] == 0


def test_idempotency_includes_edition_and_preserves_old_receipts(api):
    body = {'title':'重试','original_key':'D','fingering':{'code':'closed_2'}}
    headers = {**api.headers_for(),'Idempotency-Key':'old'}
    first = api.post('/scores/',json=body,headers=headers)
    assert first.status_code == 201
    with api.factory() as db:
        receipt = db.scalar(select(IdempotencyRecord))
        payload = deepcopy(receipt.response)
        payload.pop('edition')  # receipt from the previous deployed API
        receipt.response = payload
        db.commit()
    patch(api,first.json()['data']['id'],first.headers['etag'],{'edition':FULL})
    for extra in [{},{'edition':None},{'edition':{}}]:
        replay = api.post('/scores/',json={**body,**extra},headers=headers)
        assert replay.status_code == 201 and replay.json()['data']['edition'] == EMPTY
        assert replay.headers['etag'] == first.headers['etag']
    conflict = api.post('/scores/',json={**body,'edition':FULL},headers=headers)
    assert conflict.status_code == 409 and conflict.json()['detail']['reason'] == 'IDEMPOTENCY_CONFLICT'
    headers['Idempotency-Key']='with-edition'
    first = api.post('/scores/',json={**body,'edition':FULL},headers=headers)
    assert first.status_code == 201
    assert api.post('/scores/',json={**body,'edition':FULL},headers=headers).json() == first.json()
    assert api.post('/scores/',json={**body,'edition':{**FULL,'album':'changed'}},headers=headers).status_code == 409


def test_unknown_nested_fields_and_readonly_properties_rejected(api):
    score,tag = create(api,edition=FULL)
    for edition in [{'artist':'unknown'},{'owner_id':2},{'revision':3},{'label':123},[],42]:
        patch(api,score['id'],tag,{'edition':edition},422)
    actual = api.get(f'/scores/{score["id"]}',headers=api.headers_for())
    assert actual.headers['etag'] == tag and actual.json()['data']['edition'] == FULL


def test_openapi_includes_edition_contract(api):
    document = api.get('/openapi.json').json()
    schemas = document['components']['schemas']
    for name in ['ScoreCreate','ScorePatch','ScoreSummary','ScoreDetail']:
        assert 'edition' in schemas[name]['properties']
    edition = schemas['EditionMetadata']
    assert edition['additionalProperties'] is False
    assert set(edition['properties']) == set(EMPTY)


def test_documented_fixtures_execute_against_api(api):
    import json
    from pathlib import Path
    fixture_root = Path(__file__).parent/'fixtures'
    creations = json.loads((fixture_root/'same-title-editions.json').read_text())
    created = []
    for step in creations['steps']:
        response = api.request(step['method'],step['path'],json=step['body'],
            headers={**api.headers_for(),'Idempotency-Key':str(uuid4())})
        assert response.status_code == step['expected']['http_status']
        assert response.json()['data']['edition'] == step['body']['edition']
        created.append(response)
    assert created[0].json()['data']['id'] != created[1].json()['data']['id']
    assert created[0].json()['data']['edition']['release_date'] == '2020'
    response = created[0]
    updates = json.loads((fixture_root/'edition-patch.json').read_text())
    for step in updates['steps']:
        old = response.json()['data']['edition']
        path = step['path'].format(score_id=response.json()['data']['id'])
        response = api.request(step['method'],path,json=step['body'],headers={**api.headers_for(),'If-Match':response.headers['etag']})
        assert response.status_code == step['expected']['http_status']
        if step['body']['edition'] is None:
            assert response.json()['data']['edition'] == EMPTY
        else:
            assert response.json()['data']['edition'] == {**old,**step['body']['edition']}
