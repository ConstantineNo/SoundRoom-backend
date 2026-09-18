#!/usr/bin/env python3
"""Throttled live edition checks using an existing private deployment-test account."""
import argparse
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('base_url')
    parser.add_argument('credentials', type=Path)
    args = parser.parse_args()
    base = args.base_url.rstrip('/')
    saved = json.loads(args.credentials.read_text())
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    last_call = 0.0
    calls = 0

    def request(path, method='GET', data=None, headers=None, expected=200):
        nonlocal last_call,calls
        time.sleep(max(0,2.2-(time.monotonic()-last_call)))
        body = json.dumps(data).encode() if isinstance(data,dict) else data
        values = dict(headers or {})
        if isinstance(data,dict):values['Content-Type']='application/json'
        req = urllib.request.Request(base+path,body,values,method=method)
        last_call = time.monotonic()
        calls += 1
        try:
            with opener.open(req,timeout=20) as response:
                status,content,response_headers = response.status,response.read(),dict(response.headers)
        except urllib.error.HTTPError as error:
            status,content,response_headers = error.code,error.read(),dict(error.headers)
        assert status == expected,(path,status,content[:300])
        return json.loads(content),{key.lower():value for key,value in response_headers.items()}

    login,_ = request('/auth/login','POST',urllib.parse.urlencode({'username':saved['username'],'password':saved['password']}).encode(),
                      {'Content-Type':'application/x-www-form-urlencoded'})
    auth = {'Authorization':'Bearer '+login['access_token']}
    empty = dict.fromkeys(('label','original_artist','performer','album','release_date'))
    legacy,_ = request(f'/scores/{saved["score_id"]}',headers=auth)
    assert legacy['data']['edition'] == empty and legacy['data']['title'] == saved['title']
    marker = uuid4().hex[:10]
    edition = {'label':'现场版','original_artist':'原唱甲','performer':'表演者乙','album':'edition-'+marker,'release_date':'2020'}
    body = {'title':'[新字段验证] 同名音乐版本','original_key':'D','fingering':{'code':'closed_2'},'edition':edition,
            'classification_decision':{'method':'manual','flute_key':'A'}}
    headers = {**auth,'Idempotency-Key':str(uuid4())}
    created,h = request('/scores/','POST',body,headers,201)
    sid,tag = created['data']['id'],h['etag']
    assert created['data']['edition'] == edition
    replay,_ = request('/scores/','POST',body,headers,201)
    assert replay == created
    other = {**body,'edition':{**edition,'label':'录音室版','release_date':'2020-02'}}
    second,_ = request('/scores/','POST',other,{**auth,'Idempotency-Key':str(uuid4())},201)
    assert second['data']['id'] != sid
    query = urllib.parse.urlencode({'scope':'mine','q':'  edition-'+marker+'  '})
    listed,_ = request('/scores/?'+query,headers=auth)
    counts,_ = request('/score-categories?'+query,headers=auth)
    assert listed['data']['total'] == counts['data']['classified_score_count'] == counts['data']['total_visible_scores'] == 2
    patched,h = request(f'/scores/{sid}','PATCH',{'edition':{'album':'新专辑-'+marker,'release_date':'2020-02-29'}},{**auth,'If-Match':tag})
    changed = {**edition,'album':'新专辑-'+marker,'release_date':'2020-02-29'}
    assert patched['data']['edition'] == changed
    assert patched['data']['arrangements'] == created['data']['arrangements']
    request(f'/scores/{sid}','PATCH',{'edition':None},{**auth,'If-Match':tag},412)
    tag = h['etag']
    invalid,_ = request(f'/scores/{sid}','PATCH',{'edition':{'release_date':'2023-02-29'}},{**auth,'If-Match':tag},422)
    assert any(error['path']=='body.edition.release_date' for error in invalid['detail']['field_errors'])
    request(f'/scores/{sid}','PATCH',{'edition':{}},{**auth,'If-Match':tag},422)
    request(f'/scores/{sid}',expected=404)
    private_query = urllib.parse.urlencode({'q':'新专辑-'+marker})
    public,_ = request('/scores/?'+private_query)
    assert public['data']['total'] == 0
    copied,copy_headers = request(f'/scores/{sid}/copies','POST',{}, {**auth,'Idempotency-Key':str(uuid4())},201)
    assert copied['data']['edition'] == changed and copied['data']['visibility'] == 'private'
    copy_id = copied['data']['id']
    cleared,h = request(f'/scores/{copy_id}','PATCH',{'edition':{'release_date':None}}, {**auth,'If-Match':copy_headers['etag']})
    assert cleared['data']['edition'] == {**changed,'release_date':None}
    cleared,h = request(f'/scores/{copy_id}','PATCH',{'edition':None}, {**auth,'If-Match':h['etag']})
    assert cleared['data']['edition'] == empty
    original,_ = request(f'/scores/{sid}',headers=auth)
    assert original['data']['edition'] == changed
    published,h = request(f'/scores/{copy_id}/publish','POST',headers={**auth,'If-Match':h['etag']})
    assert published['data']['edition'] == empty
    unpublished,_ = request(f'/scores/{copy_id}/unpublish','POST',headers={**auth,'If-Match':h['etag']})
    assert unpublished['data']['edition'] == empty
    request(f'/scores/{copy_id}',expected=404)
    spec,_ = request('/openapi.json')
    for name in ('ScoreCreate','ScorePatch','ScoreSummary','ScoreDetail'):
        assert 'edition' in spec['components']['schemas'][name]['properties']
    print(json.dumps({'passed':True,'base_url':base,'requests':calls,'minimum_interval_seconds':2.2,
        'legacy_score_id':saved['score_id'],'new_private_score_ids':[sid,second['data']['id'],copy_id],
        'checks':['legacy fields preserved with null edition','same-title distinct ids','all five fields',
            'year/month/day precision','invalid leap day field error','PATCH merge/null/empty','classification unchanged',
            'ETag stale rejection','idempotent create','query/count consistency','private data isolation',
            'copy independence','publish/unpublish','live OpenAPI fields']}))


if __name__ == '__main__':
    main()
