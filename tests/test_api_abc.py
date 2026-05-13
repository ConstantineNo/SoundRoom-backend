
import sys
import os
import io

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app


def _register_and_login(client: TestClient):
    client.post("/auth/register", json={"username": "abcuser", "password": "test123"})
    resp = client.post("/auth/login", data={"username": "abcuser", "password": "test123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_api_abc_update():
    client = TestClient(app)
    headers = _register_and_login(client)

    files = {
        'image': ('test.jpg', io.BytesIO(b'fake image data'), 'image/jpeg'),
        'audio': ('test.mp3', io.BytesIO(b'fake audio data'), 'audio/mpeg')
    }
    data = {
        'title': 'Test REST API',
        'song_key': 'C',
        'flute_key': 'C',
        'fingering': 'C'
    }

    print("Creating score...")
    response = client.post("/scores/", data=data, files=files, headers=headers)
    if response.status_code != 200:
        print(f"Failed to create score: {response.text}")
        return

    score_id = response.json()['id']
    print(f"Score created with ID: {score_id}")

    abc_content = "X:1\nT:Updated ABC\nK:G\nM:4/4\nL:1/4\n| G A B c |"
    print("Updating ABC...")
    response = client.put(f"/scores/{score_id}/abc", json={"abc_content": abc_content}, headers=headers)

    if response.status_code != 200:
        print(f"Failed to update ABC: {response.text}")
        raise Exception("API Update failed")

    result = response.json()
    assert result['abc_source'] == abc_content
    assert result['structured_data']['meta']['key'] == 'G major'
    print("ABC Update successful!")

    print("Verifying persistence...")
    response = client.get(f"/scores/{score_id}")
    result = response.json()
    assert result['abc_source'] == abc_content
    print("Persistence verified!")


if __name__ == "__main__":
    try:
        test_api_abc_update()
    except Exception as e:
        print(f"API Test failed: {e}")
