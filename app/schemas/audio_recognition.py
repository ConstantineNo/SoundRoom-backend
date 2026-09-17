"""Versioned, database-independent recognition contract. Times are decoded-audio seconds."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class RecognitionConfig(Contract):
    sample_rate: int = Field(default=22050, ge=8000, le=48000)
    frame_length: int = Field(default=2048, ge=512, le=8192)
    hop_length: int = Field(default=220, ge=64, le=2048)
    fmin: float = Field(default=65.406, ge=40, le=2000)
    fmax: float = Field(default=2093.005, ge=80, le=5000)
    resolution: float = Field(default=0.1, ge=0.05, le=0.5)
    voiced_threshold: float = Field(default=0.1, ge=0, le=1)
    silence_db: float = Field(default=-50, ge=-100, le=-6)
    min_note_seconds: float = Field(default=0.08, ge=0.02, le=1)
    pitch_change_cents: float = Field(default=75, ge=30, le=300)
    stable_seconds: float = Field(default=0.05, ge=0.02, le=0.5)
    onset_ratio: float = Field(default=2.5, ge=1.5, le=10)

    @model_validator(mode="after")
    def consistent(self):
        if not self.fmin < self.fmax < self.sample_rate / 2:
            raise ValueError("Require fmin < fmax < Nyquist")
        if self.frame_length < 2 * self.sample_rate / self.fmin:
            raise ValueError("frame_length must cover at least two periods of fmin")
        if self.hop_length > self.frame_length // 2:
            raise ValueError("hop_length must be <= frame_length / 2")
        return self


class AudioInfo(Contract):
    sample_rate: int = Field(gt=0)
    samples: int = Field(gt=0)
    channels: int = Field(ge=1, le=2)
    duration_seconds: float = Field(gt=0)
    sha256: str
    peak_amplitude: float = Field(ge=0)
    clipped_fraction: float = Field(ge=0, le=1)
    channel_mix: str = "arithmetic mean; no normalization"


class PitchFrame(Contract):
    index: int = Field(ge=0)
    time_seconds: float = Field(ge=0)
    source_sample: int = Field(ge=0)
    raw_f0_hz: float | None = Field(gt=0)
    f0_hz: float | None = Field(gt=0)
    engine_voiced: bool
    voiced: bool
    voiced_probability: float = Field(ge=0, le=1)
    rms_db: float
    onset_strength: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def voicing_consistent(self):
        if self.voiced != (self.f0_hz is not None):
            raise ValueError("Accepted F0 must be null exactly when unvoiced")
        return self


class NoteEvent(Contract):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    start_frame: int = Field(ge=0)
    end_frame_exclusive: int = Field(gt=0)
    frequency_hz: float = Field(gt=0)
    midi_float: float
    nearest_note: str
    cents_from_nearest: float
    median_voiced_probability: float = Field(ge=0, le=1)
    start_reason: Literal["voicing", "pitch_change", "energy_onset"]
    flags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ordered(self):
        if self.end_seconds <= self.start_seconds or self.end_frame_exclusive <= self.start_frame:
            raise ValueError("Note end must follow start in both seconds and frames")
        return self


class RunInfo(Contract):
    engine: str = "librosa.pyin"
    implementation_version: str = "soundroom-pyin-segmentation-1.0"
    engine_version: str
    config: RecognitionConfig
    elapsed_seconds: float
    real_time_factor: float
    versions: dict[str, str]
    reliability_kind: str = "pYIN voiced_probability; NOT pitch correctness probability"
    time_origin: str = "decoded sample 0; center=True; frame i at i*hop/sample_rate"
    boundary_resolution_seconds: float
    weights: str = "none (pYIN statistical algorithm)"


class RecognitionResult(Contract):
    schema_version: Literal["1.0"] = "1.0"
    audio: AudioInfo
    run: RunInfo
    frames: list[PitchFrame]
    notes: list[NoteEvent]
    warnings: list[str]


class Annotation(Contract):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    frequency_hz: float = Field(gt=0)
    label: str = ""

    @model_validator(mode="after")
    def ordered(self):
        if self.end_seconds <= self.start_seconds:
            raise ValueError("Annotation end must be after start")
        return self
