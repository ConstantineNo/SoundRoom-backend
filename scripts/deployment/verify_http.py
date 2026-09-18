#!/usr/bin/env python3
"""HTTP smoke checks; credentials stay in a mode-0600 workspace state file."""
import argparse
import base64
import json
from pathlib import Path
import secrets
import urllib.error
import urllib.parse
import urllib.request
import uuid


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('base_url')
    parser.add_argument('state_file', type=Path)
    parser.add_argument('--recheck', action='store_true')
    args = parser.parse_args()
    base = args.base_url.rstrip('/')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(path, method='GET', data=None, headers=None, expected=200):
        body = json.dumps(data).encode() if isinstance(data, dict) else data
        hdrs = headers.copy() if headers else {}
        if isinstance(data, dict):
            hdrs['Content-Type'] = 'application/json'
        req = urllib.request.Request(base+path, data=body, method=method, headers=hdrs)
        try:
            with opener.open(req, timeout=20) as response:
                code, response_headers, content = response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as error:
            code, response_headers, content = error.code, dict(error.headers), error.read()
        assert code == expected, (path, code, content[:300])
        return content, {k.lower():v for k,v in response_headers.items()}

    if args.recheck:
        state = json.loads(args.state_file.read_text())
        auth = {'Authorization':'Bearer '+state['token']}
        result, headers = request('/scores/'+str(state['score_id']), headers=auth)
        assert json.loads(result)['data']['title'] == state['title']
        assert headers['etag'] == state['etag']
        content, _ = request(f'/scores/{state["score_id"]}/assets/{state["asset_id"]}', headers=auth)
        assert base64.b64encode(content).decode() == state['image_base64']
        request('/scores/'+str(state['score_id']), expected=404)
        print(json.dumps({'checks':'post-restart data, asset, ETag, JWT and privacy', 'passed':True, 'score_id':state['score_id']}))
        return

    request('/health')
    options, _ = request('/score-classification-options')
    assert len(json.loads(options)['data']['flute_keys']) == 12
    assert len(json.loads(options)['data']['fingerings']) == 8
    schema, _ = request('/openapi.json')
    assert '/score-categories' in json.loads(schema)['paths']
    username = 'deploy_check_'+uuid.uuid4().hex[:12]
    password = secrets.token_urlsafe(24)
    request('/auth/register', 'POST', {'username':username, 'password':password})
    login, _ = request('/auth/login', 'POST', urllib.parse.urlencode({'username':username,'password':password}).encode(),
                       {'Content-Type':'application/x-www-form-urlencoded'})
    token = json.loads(login)['access_token']
    auth = {'Authorization':'Bearer '+token}
    request('/auth/me', headers=auth)
    candidate, _ = request('/flute-key-candidates', 'POST', {'original_key':'D','fingering':{'code':'closed_2'}}, auth)
    candidate = json.loads(candidate)['data']
    assert candidate['candidates'][0]['flute_key'] == 'A'
    title = '[部署验证] 私有分类与持久化'
    body = {'title':title,'original_key':'D','fingering':{'code':'closed_2'},
            'classification_decision':{'method':'candidate','flute_key':'A','candidate_token':candidate['candidate_token']}}
    create_headers = {**auth, 'Idempotency-Key':str(uuid.uuid4()), 'Origin':'http://localhost:5173'}
    created, headers = request('/scores/', 'POST', body, create_headers, 201)
    score = json.loads(created)['data']
    sid, tag = score['id'], headers['etag']
    assert 'etag' in headers['access-control-expose-headers'].lower()
    assert headers['access-control-allow-origin'] == '*'
    retried, _ = request('/scores/', 'POST', body, create_headers, 201)
    assert retried == created
    request(f'/scores/{sid}', expected=404)
    groups, _ = request('/score-categories?scope=mine', headers=auth)
    assert json.loads(groups)['data']['classified_score_count'] == 1
    listing, _ = request('/scores/?scope=mine&flute_key=A&fingering=closed_2&match=whole', headers=auth)
    assert json.loads(listing)['data']['items'][0]['id'] == sid
    request(f'/scores/{sid}', 'PATCH', {'notes':'requires If-Match'}, auth, 428)
    request(f'/scores/{sid}', 'PATCH', {'notes':'stale'}, {**auth,'If-Match':'"stale"'}, 412)
    request(f'/scores/{sid}', 'OPTIONS', headers={'Origin':'http://localhost:5173',
        'Access-Control-Request-Method':'PATCH','Access-Control-Request-Headers':'authorization,if-match'})
    # Valid PNG created in memory; no temporary asset files.
    from PIL import Image
    from io import BytesIO
    image = BytesIO()
    Image.new('RGB',(2,2),'white').save(image,'PNG')
    image = image.getvalue()
    boundary = uuid.uuid4().hex
    multipart = (f'--{boundary}\r\nContent-Disposition: form-data; name="purpose"\r\n\r\nscore_image\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="check.png"\r\nContent-Type: image/png\r\n\r\n').encode()+image+f'\r\n--{boundary}--\r\n'.encode()
    uploaded, headers = request(f'/scores/{sid}/assets', 'POST', multipart,
        {**auth,'If-Match':tag,'Idempotency-Key':str(uuid.uuid4()),'Content-Type':'multipart/form-data; boundary='+boundary}, 201)
    aid = json.loads(uploaded)['data']['id']
    tag = headers['etag']
    content, asset_headers = request(f'/scores/{sid}/assets/{aid}', headers=auth)
    assert content == image and asset_headers['cache-control'] == 'private, no-store'
    request(f'/scores/{sid}/assets/{aid}', expected=404)
    capability, _ = request(f'/scores/{sid}/arrangements/{score["arrangements"][0]["id"]}/practice-capability', headers=auth)
    assert not json.loads(capability)['data']['available']
    args.state_file.parent.mkdir(parents=True,exist_ok=True)
    with open(args.state_file, 'x', opener=lambda path, flags: __import__('os').open(path,flags,0o600)) as stream:
        json.dump({'username':username,'password':password,'token':token,'score_id':sid,'asset_id':aid,
                   'etag':tag,'title':title,'image_base64':base64.b64encode(image).decode()},stream)
    print(json.dumps({'passed':True,'base_url':base,'score_id':sid,'checks':[
        'health','dictionary','openapi','register/login','candidate confirmation','private create/read',
        'idempotency replay','categories/whole match','428/412','CORS/ETag','private asset upload/download','practice not available']}))


if __name__ == '__main__':
    main()
