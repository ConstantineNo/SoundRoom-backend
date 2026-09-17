"""Bounded audio decoding; no uploads, database access or temporary audio files."""
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import BinaryIO

import numpy as np
import soundfile as sf

from app.schemas.audio_recognition import AudioInfo

MAX_SECONDS = 60
MAX_BYTES = 32 * 1024 * 1024
MAX_CHANNELS = 2


class AudioInputError(ValueError):
    pass


@dataclass(frozen=True)
class AudioBuffer:
    mono: np.ndarray
    info: AudioInfo
    peak: float
    clipped_fraction: float
    source_pcm: np.ndarray


def from_pcm(samples: np.ndarray, sample_rate: int) -> AudioBuffer:
    data = np.asarray(samples, dtype=np.float32)
    if data.ndim == 1:
        data = data[:, None]
    if data.ndim != 2 or not 1 <= data.shape[1] <= MAX_CHANNELS:
        raise AudioInputError("Only mono/stereo PCM is supported")
    if not 8000 <= sample_rate <= 192000:
        raise AudioInputError("Sample rate must be 8000–192000 Hz")
    if not 0 < len(data) <= sample_rate * MAX_SECONDS:
        raise AudioInputError(f"Audio must be nonempty and <= {MAX_SECONDS} seconds")
    if not np.isfinite(data).all():
        raise AudioInputError("PCM contains NaN or infinity")
    peak = float(np.max(np.abs(data)))
    clipped = float(np.mean(np.abs(data) >= 0.999))
    digest = hashlib.sha256()
    digest.update(f"{sample_rate}:{data.shape}".encode())
    digest.update(np.ascontiguousarray(data, dtype='<f4').tobytes())
    mono = np.mean(data, axis=1, dtype=np.float32)
    mono.setflags(write=False)
    source_pcm = np.array(data, dtype=np.float32, order="C", copy=True)
    source_pcm.setflags(write=False)
    return AudioBuffer(mono, AudioInfo(
        sample_rate=sample_rate, samples=len(data), channels=data.shape[1],
        duration_seconds=len(data) / sample_rate, sha256=digest.hexdigest(),
        peak_amplitude=peak, clipped_fraction=clipped,
    ), peak, clipped, source_pcm)


def load_audio(source: str | Path | BinaryIO) -> AudioBuffer:
    try:
        if isinstance(source, (str, Path)) and Path(source).stat().st_size > MAX_BYTES:
            raise AudioInputError("File exceeds 32 MiB")
        with sf.SoundFile(source) as audio:
            if audio.format not in {"WAV", "WAVEX", "FLAC", "AIFF", "OGG"}:
                raise AudioInputError("Supported containers: WAV, FLAC, AIFF, OGG")
            if not 8000 <= audio.samplerate <= 192000 or not 1 <= audio.channels <= 2:
                raise AudioInputError("Unsupported sample rate or channel count")
            if not 0 < audio.frames <= audio.samplerate * MAX_SECONDS:
                raise AudioInputError(f"Audio must be nonempty and <= {MAX_SECONDS} seconds")
            return from_pcm(audio.read(dtype="float32", always_2d=True), audio.samplerate)
    except (OSError, RuntimeError) as exc:
        raise AudioInputError(f"Cannot decode audio: {exc}") from exc
