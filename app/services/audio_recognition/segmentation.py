"""Candidate note segmentation. No tuning correction or rhythmic quantization."""
import numpy as np
from app.schemas.audio_recognition import NoteEvent, PitchFrame, RecognitionConfig


def segment_notes(frames: list[PitchFrame], duration: float,
                  config: RecognitionConfig) -> list[NoteEvent]:
    hop = config.hop_length / config.sample_rate
    stable = max(2, round(config.stable_seconds / hop))
    transition = max(1, round(config.frame_length / config.hop_length / 2))
    minimum = max(2, int(np.ceil(config.min_note_seconds / hop)))
    hz = np.array([f.f0_hz if f.voiced else np.nan for f in frames], dtype=float)
    midi = 69 + 12 * np.log2(hz / 440)
    energy = np.array([10 ** (f.rms_db / 20) for f in frames])
    voiced = np.isfinite(hz)
    changes = np.diff(np.r_[False, voiced, False].astype(int))
    events = []
    for begin, end in zip(np.flatnonzero(changes == 1), np.flatnonzero(changes == -1)):
        cuts = [(int(begin), "voicing")]
        i = begin + minimum
        while i <= end - minimum:
            # Centered F0 windows smear a legato step across roughly one frame_length.
            # Compare stable plateaus on either side of that transition, not its slope.
            left = midi[max(cuts[-1][0], i - transition - stable):max(cuts[-1][0], i - transition)]
            right = midi[min(end, i + transition):min(end, i + transition + stable)]
            stable_spread = min(35, config.pitch_change_cents * .4)
            pitch_jump = (len(left) >= stable and len(right) >= stable
                          and abs(np.median(right) - np.median(left)) * 100 >= config.pitch_change_cents
                          and np.ptp(left) * 100 < stable_spread
                          and np.ptp(right) * 100 < stable_spread)
            # A same-pitch rearticulation needs an energy valley AND renewed onset.
            valley = energy[i]
            prior = np.max(energy[max(begin, i - stable):i])
            after = np.max(energy[i:min(end, i + stable)])
            energy_onset = (valley > 0 and min(prior, after) / valley >= config.onset_ratio
                            and frames[min(i + 1, len(frames) - 1)].onset_strength > 0)
            if pitch_jump or energy_onset:
                cuts.append((int(i), "pitch_change" if pitch_jump else "energy_onset"))
                i += minimum
            else:
                i += 1
        for j, (start, reason) in enumerate(cuts):
            stop = cuts[j + 1][0] if j + 1 < len(cuts) else int(end)
            if stop - start < minimum:
                continue
            estimate = float(np.median(midi[start:stop]))
            frequency = float(440 * 2 ** ((estimate - 69) / 12))
            nearest = int(np.floor(estimate + 0.5))
            name = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][nearest % 12]
            flags = ["candidate_boundary"]
            if np.percentile(midi[start:stop], 90) - np.percentile(midi[start:stop], 10) > 0.6:
                flags.append("variable_pitch_or_glide")
            probability = float(np.median([f.voiced_probability for f in frames[start:stop]]))
            if probability < 0.5:
                flags.append("low_voicing_probability")
            events.append(NoteEvent(
                start_seconds=start * hop, end_seconds=min(stop * hop, duration),
                start_frame=start, end_frame_exclusive=stop,
                frequency_hz=frequency, midi_float=estimate, nearest_note=f"{name}{nearest // 12 - 1}",
                cents_from_nearest=(estimate - nearest) * 100,
                median_voiced_probability=probability, start_reason=reason, flags=flags,
            ))
    return events
