"""Deterministic synthetic fixtures. These are not real flute/voice quality evidence."""
from dataclasses import dataclass
from pathlib import Path
import json
import numpy as np
import soundfile as sf
from app.schemas.audio_recognition import Annotation


@dataclass
class SyntheticCase:
    name: str
    sample_rate: int
    samples: np.ndarray
    notes: list[Annotation]
    expected_hz: np.ndarray


def cases() -> list[SyntheticCase]:
    result = []
    specifications = [
        ("detuned_44100", 44100, [(0.2, .9, 440 * 2 ** (23 / 1200)), (1.1, 1.8, 659.255)]),
        ("repeated_48000", 48000, [(.2, .8, 440), (1.0, 1.7, 440)]),
        ("legato", 22050, [(.2, 1., 440), (1., 1.8, 523.251)]),
        ("octaves", 22050, [(.2, .9, 220), (1.1, 1.8, 880)]),
        ("amplitude", 22050, [(.2, 1.8, 440)]),
        ("vibrato", 22050, [(.2, 1.8, 440)]),
        ("glide", 22050, [(.2, 1.8, 440)]),
        ("rearticulated", 22050, [(.2, 1., 440), (1., 1.8, 440)]),
    ]
    for name, sr, notes in specifications:
        t = np.arange(round(2 * sr)) / sr
        y = np.zeros(len(t), np.float32)
        truth = np.full(len(t), np.nan)
        annotations = []
        for start, end, hz in notes:
            mask = (t >= start) & (t < end)
            tt = t[mask] - start
            freq = np.full(len(tt), hz)
            amplitude = np.full(len(tt), .4)
            if name == "vibrato":
                freq = hz * 2 ** (25 * np.sin(2 * np.pi * 5 * tt) / 1200)
            if name == "glide":
                freq = hz * 2 ** (300 * tt / (end - start) / 1200)
            if name == "amplitude":
                amplitude *= .6 + .4 * np.cos(2 * np.pi * .7 * tt)
            # Raised edges except the legato change; same-pitch rearticulation has a short valley.
            if name != "legato":
                fade = .025 if name == "rearticulated" else .01
                amplitude *= np.minimum(1, np.minimum(tt / fade, (end - start - tt) / fade))
            phase = 2 * np.pi * np.cumsum(freq) / sr
            y[mask] = amplitude * np.sin(phase)
            truth[mask] = freq
            annotations.append(Annotation(start_seconds=start, end_seconds=end, frequency_hz=hz, label=name))
        result.append(SyntheticCase(name, sr, y, annotations, truth))
    sr = 22050
    result.append(SyntheticCase("silence", sr, np.zeros(sr, np.float32), [], np.full(sr, np.nan)))
    rng = np.random.default_rng(20260918)
    result.append(SyntheticCase("noise", sr, rng.normal(0, .05, sr).astype(np.float32), [], np.full(sr, np.nan)))
    return result


def write_case(case: SyntheticCase, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{case.name}.wav"
    sf.write(path, case.samples, case.sample_rate, subtype="FLOAT")
    path.with_suffix(".annotations.json").write_text(json.dumps([a.model_dump() for a in case.notes], indent=2))
    return path
