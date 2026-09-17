from io import BytesIO
import json
import sys
import numpy as np
import pytest
import soundfile as sf
from pydantic import ValidationError
from app.schemas.audio_recognition import RecognitionConfig, RecognitionResult
from app.services.audio_recognition import analyze, from_pcm, load_audio, AudioInputError
from tools.recognition_lab.synthetic import cases
from tools.recognition_lab.evaluate import note_metrics


def test_silence_and_json():
    result = analyze(from_pcm(np.zeros(22050), 22050))
    assert result.notes == []
    assert all(f.f0_hz is None and not f.voiced for f in result.frames)
    assert RecognitionResult.model_validate_json(result.model_dump_json()) == result
    assert "NaN" not in result.model_dump_json()
    assert "app.core.database" not in sys.modules


@pytest.mark.parametrize("kwargs", [{"fmin": 900, "fmax": 800}, {"fmin": 40, "frame_length": 512},
                                     {"resolution": .001}, {"hop_length": 2048}, {"silence_db": float('nan')}, {"unknown": 1}])
def test_invalid_config(kwargs):
    with pytest.raises(ValidationError):
        RecognitionConfig(**kwargs)


@pytest.mark.parametrize("samples,sr", [(np.array([]), 22050), (np.array([np.nan]), 22050),
    (np.zeros((10, 3)), 22050), (np.zeros(10), 7000), (np.zeros(8000 * 61), 8000)])
def test_bad_pcm(samples, sr):
    with pytest.raises(AudioInputError):
        from_pcm(samples, sr)


def test_corrupt_file():
    with pytest.raises(AudioInputError):
        load_audio(BytesIO(b"not audio"))


def test_empty_file():
    data = BytesIO()
    sf.write(data, np.zeros(0), 22050, format="WAV")
    data.seek(0)
    with pytest.raises(AudioInputError):
        load_audio(data)


def test_stereo_mix_and_clipping():
    data = np.column_stack((np.ones(2205), -np.ones(2205)))
    audio = from_pcm(data, 22050)
    result = analyze(audio)
    assert np.max(np.abs(audio.mono)) == 0
    assert "clipping_detected" in result.warnings
    assert any("stereo" in w for w in result.warnings)


@pytest.mark.parametrize("name", ["detuned_44100", "repeated_48000", "legato", "octaves", "amplitude", "vibrato", "rearticulated"])
def test_known_notes_and_timing(name):
    case = next(c for c in cases() if c.name == name)
    result = analyze(from_pcm(case.samples, case.sample_rate))
    metrics = note_metrics(result.notes, case.notes)
    assert metrics["f1"] == 1, (name, metrics, result.notes)
    for frame in result.frames:
        assert frame.time_seconds == pytest.approx(frame.index * 220 / 22050)
        assert abs(frame.source_sample / case.sample_rate - frame.time_seconds) <= 1 / case.sample_rate
    if name == "detuned_44100":
        assert 15 < result.notes[0].cents_from_nearest < 35  # must not be rounded to A4


def test_short_clip_no_negative_time():
    result = analyze(from_pcm(np.zeros(10), 22050))
    assert all(0 <= f.time_seconds < result.audio.duration_seconds for f in result.frames)
