"""Pure recognition service shared by GUI, CLI and the optional HTTP adapter."""
from importlib.metadata import version
import time

import librosa
import numpy as np

from app.schemas.audio_recognition import PitchFrame, RecognitionConfig, RecognitionResult, RunInfo
from .audio import AudioBuffer
from .segmentation import segment_notes


def analyze(audio: AudioBuffer, config: RecognitionConfig | None = None) -> RecognitionResult:
    config = config or RecognitionConfig()
    started = time.perf_counter()
    y = librosa.resample(audio.mono, orig_sr=audio.info.sample_rate,
                         target_sr=config.sample_rate, res_type="soxr_hq")
    hop = config.hop_length
    count = int(np.ceil(len(y) / hop))
    # Short energy windows give silence boundaries independently of the pYIN window.
    rms = librosa.feature.rms(y=y, frame_length=2 * hop, hop_length=hop, center=True)[0][:count]
    db = 20 * np.log10(np.maximum(rms, 1e-10))
    warnings = []
    analysis_y = y
    if len(y) < config.frame_length:
        warnings.append("shorter_than_analysis_window; limited_pitch_evidence")
        analysis_y = np.pad(y, (0, config.frame_length - len(y)))
    if audio.info.channels > 1:
        warnings.append("stereo_mixed_to_mono; opposite-phase channels may cancel")
    if audio.clipped_fraction > 0.001:
        warnings.append("clipping_detected")
    if np.max(db) < config.silence_db:
        f0, flag, probability = np.full(count, np.nan), np.zeros(count, bool), np.zeros(count)
        warnings.append("silence_or_below_energy_gate")
    else:
        f0, flag, probability = librosa.pyin(
            analysis_y, sr=config.sample_rate, fmin=config.fmin, fmax=config.fmax,
            frame_length=config.frame_length, hop_length=hop,
            resolution=config.resolution, center=True, fill_na=np.nan,
        )
        f0, flag, probability = f0[:count], flag[:count], probability[:count]
    # Spectral positive flux is supporting evidence, never a pitch correctness score.
    spectrum = np.abs(librosa.stft(analysis_y, n_fft=config.frame_length, hop_length=hop))[:, :count]
    flux = np.r_[0, np.maximum(0, np.diff(spectrum, axis=1)).sum(axis=0)]
    flux = flux / max(float(np.max(flux)), 1e-10)
    frames = []
    for i in range(count):
        raw = float(f0[i]) if np.isfinite(f0[i]) else None
        accepted = bool(flag[i] and raw is not None and probability[i] >= config.voiced_threshold
                        and db[i] >= config.silence_db)
        t = i * hop / config.sample_rate
        frames.append(PitchFrame(
            index=i, time_seconds=t,
            source_sample=min(audio.info.samples - 1, round(t * audio.info.sample_rate)),
            raw_f0_hz=raw, f0_hz=raw if accepted else None,
            engine_voiced=bool(flag[i]), voiced=accepted,
            voiced_probability=float(np.clip(probability[i], 0, 1)),
            rms_db=float(db[i]), onset_strength=float(flux[i]),
        ))
    notes = segment_notes(frames, audio.info.duration_seconds, config)
    if not notes and "silence_or_below_energy_gate" not in warnings:
        warnings.append("no_stable_note_candidates")
    if any(f.engine_voiced and not f.voiced for f in frames):
        warnings.append("some_engine_frames_rejected_by_probability_or_energy_gate")
    warnings.append("monophonic_only; out_of_range_pitch_is_not_reliably_detected")
    elapsed = time.perf_counter() - started
    return RecognitionResult(audio=audio.info, frames=frames, notes=notes, warnings=warnings,
        run=RunInfo(engine_version=librosa.__version__, config=config, elapsed_seconds=elapsed,
                    real_time_factor=elapsed / audio.info.duration_seconds,
                    versions={name: version(name) for name in ["numpy", "scipy", "librosa", "soundfile", "pydantic", "soxr", "numba"]},
                    boundary_resolution_seconds=hop / config.sample_rate))
