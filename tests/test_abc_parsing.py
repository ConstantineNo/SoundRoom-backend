
import sys
import os
import json

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.score_service import parse_abc_to_json

def test_parsing():
    abc_content = """X:1
T:Test Scale
C:Composer
K:C
M:4/4
L:1/4
| C D E F |"""
    
    try:
        result = parse_abc_to_json(abc_content)
        print("Result:", json.dumps(result, indent=2))

        # Verify Metadata
        assert result['meta']['title'] == 'Test Scale'
        assert result['meta']['key'] == 'C major' 
        
        # Verify Notes
        measures = result['measures']
        assert len(measures) == 1
        notes = measures[0]['notes']
        assert len(notes) == 4
        assert notes[0]['pitch'] == 'C4'
        assert notes[1]['pitch'] == 'D4'
        assert notes[2]['pitch'] == 'E4'
        assert notes[3]['pitch'] == 'F4'
        
        print("Parsing test passed!")
        
    except Exception as e:
        print(f"Test failed: {e}")
        # raise e

if __name__ == "__main__":
    test_parsing()
