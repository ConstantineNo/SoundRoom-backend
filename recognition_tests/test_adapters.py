from io import BytesIO
import json
import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient
from app.services.audio_recognition import analyze, load_audio
from tools.recognition_lab.api import api
from tools.recognition_lab.cli import main
from tools.recognition_lab.synthetic import cases, write_case


def test_cli_reproducible_and_export(tmp_path):
    path = write_case(cases()[0], tmp_path)
    output = tmp_path / 'result.json'
    assert main([str(path), '--output', str(output)]) == 0
    cli = json.loads(output.read_text())
    direct = analyze(load_audio(path)).model_dump()
    assert cli['frames'] == direct['frames']
    assert cli['notes'] == direct['notes']
    assert cli['audio'] == direct['audio']
    assert main([str(path), '--output', str(output), '--params', str(output.with_suffix('.params.json'))]) == 0
    assert output.with_suffix('.frames.csv').is_file()
    assert output.with_suffix('.notes.csv').is_file()
    assert main([str(tmp_path / 'missing.wav'), '--output', str(output)]) == 2


def test_api_without_business_app():
    data = BytesIO()
    sf.write(data, np.zeros(2205), 22050, format='WAV')
    with TestClient(api) as client:
        response = client.post('/recognize', content=data.getvalue(), headers={'content-type': 'audio/wav'})
        assert response.status_code == 200
        assert response.json()['notes'] == []
        assert client.post('/recognize', content=b'bad').status_code == 422
        assert client.post('/recognize?params={"fmin":9999}', content=data.getvalue()).status_code == 422
        assert client.post('/recognize', content=b'x' * (32 * 1024 * 1024 + 1)).status_code == 413
