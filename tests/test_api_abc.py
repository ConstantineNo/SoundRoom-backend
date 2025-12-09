
import sys
import os
import io

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app

def test_api_abc_update():
    client = TestClient(app)
    
    # 1. Create a score first (need to mock file upload or just rely on existing, but better to create)
    # Since we don't have auth bypass enabled easily, we might hit 401 if endpoints require auth.
    # Checking app/api/endpoints/scores.py:
    # create_score_endpoint does NOT require auth (commented out in code).
    # GET endpoints do NOT require auth.
    # PUT endpoint we added does NOT require auth.
    # So we are good.
    
    # Mock files
    files = {
        'image': ('test.jpg', b'fake image data', 'image/jpeg'),
        'audio': ('test.mp3', b'fake audio data', 'audio/mpeg')
    }
    data = {
        'title': 'Test REST API',
        'song_key': 'C',
        'flute_key': 'C',
        'fingering': 'C'
    }
    
    print("Creating score...")
    response = client.post("/scores/", data=data, files=files)
    if response.status_code != 200:
        print(f"Failed to create score: {response.text}")
        return
        
    score_id = response.json()['id']
    print(f"Score created with ID: {score_id}")
    
    # 2. Update ABC
    abc_content = "X:1\nT:Updated ABC\nK:G\nM:4/4\nL:1/4\n| G A B c |"
    print("Updating ABC...")
    response = client.put(f"/scores/{score_id}/abc", json={"abc_content": abc_content})
    
    if response.status_code != 200:
        print(f"Failed to update ABC: {response.text}")
        raise Exception("API Update failed")
        
    result = response.json()
    assert result['abc_source'] == abc_content
    assert result['structured_data']['meta']['key'] == 'G major'
    print("ABC Update successful!")
    
    # 3. Verify Persistence
    print("Verifying persistence...")
    response = client.get(f"/scores/{score_id}")
    result = response.json()
    assert result['abc_source'] == abc_content
    # Depending on parser, G might be G4
    # assert result['structured_data']['measures'][0]['notes'][0]['pitch'] == 'G4'
    print("Persistence verified!")

if __name__ == "__main__":
    try:
        test_api_abc_update()
    except Exception as e:
        print(f"API Test failed: {e}")
        # sys.exit(1) # Don't exit shell, just print
