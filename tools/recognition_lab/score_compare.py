"""Compare existing recognition results with a draft beat-based score reference.

Reports score agreement, NOT performance accuracy. No time warping or pitch correction.
"""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.audio_recognition import Annotation, RecognitionResult


class ScoreNote(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    beat: float = Field(ge=0)
    duration_beats: float = Field(gt=0)
    midi: float = Field(ge=0, le=127)
    label: str
    uncertain: bool = False


class ScoreRest(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    beat: float = Field(ge=0)
    duration_beats: float = Field(gt=0)
    label: str = '谱面休止（不等于录音静音）'


class ScoreReference(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    name: str
    status: str
    audio_file: str
    audio_sha256: str
    key: str
    meter: str
    bpm: float = Field(gt=0)
    offset_seconds: float = Field(ge=0)
    timing_uncertainty_seconds: float = Field(ge=0)
    interior_margin_seconds: float = Field(ge=0)
    register_assumption: str
    evidence: str
    notes: list[ScoreNote] = Field(min_length=1)
    rests: list[ScoreRest] = Field(default_factory=list)
    comparison_policy: str = 'Structural melody reference only; unnotated ornaments and transitions are not automatically errors.'

    @model_validator(mode='after')
    def ordered(self):
        for a, b in zip(self.notes, self.notes[1:]):
            if a.beat + a.duration_beats > b.beat + 1e-9:
                raise ValueError('Score notes must be ordered and not overlap; merge ties explicitly')
        spans = sorted([*self.notes, *self.rests], key=lambda n: n.beat)
        if any(a.beat + a.duration_beats > b.beat + 1e-9 for a, b in zip(spans, spans[1:])):
            raise ValueError('Notes and score rests must not overlap')
        return self

    def annotations(self):
        return [Annotation(start_seconds=self.offset_seconds + n.beat * 60 / self.bpm,
                           end_seconds=self.offset_seconds + (n.beat + n.duration_beats) * 60 / self.bpm,
                           frequency_hz=440 * 2 ** ((n.midi - 69) / 12),
                           label=f'谱面近似 {n.label}' + (' [待核]' if n.uncertain else '')) for n in self.notes]


def compare(result: RecognitionResult, reference: ScoreReference) -> dict:
    if result.audio.sha256 != reference.audio_sha256:
        raise ValueError('Reference belongs to different decoded audio; refusing to compare')
    annotations = reference.annotations()
    rest_spans = [(reference.offset_seconds + r.beat * 60 / reference.bpm,
                   reference.offset_seconds + (r.beat + r.duration_beats) * 60 / reference.bpm) for r in reference.rests]
    end = max([a.end_seconds for a in annotations] + [b for _, b in rest_spans])
    if end > result.audio.duration_seconds:
        raise ValueError('Reference extends beyond the audio')
    times = np.array([f.time_seconds for f in result.frames])
    raw = np.array([f.raw_f0_hz if f.raw_f0_hz is not None else np.nan for f in result.frames])
    accepted = np.array([f.f0_hz if f.f0_hz is not None else np.nan for f in result.frames])
    start = min([annotations[0].start_seconds] + [a for a, _ in rest_spans])
    scope = (times >= start) & (times < end)
    rows = []
    for score, annotation in zip(reference.notes, annotations):
        inside = ((times >= annotation.start_seconds + reference.interior_margin_seconds)
                  & (times < annotation.end_seconds - reference.interior_margin_seconds))
        raw_valid = inside & np.isfinite(raw)
        valid = inside & np.isfinite(accepted)
        raw_cents = 1200 * np.log2(raw[raw_valid] / annotation.frequency_hz)
        cents = 1200 * np.log2(accepted[valid] / annotation.frequency_hz)
        overlapping = [n for n in result.notes if n.start_seconds < annotation.end_seconds
                       and n.end_seconds > annotation.start_seconds]
        rows.append(dict(label=score.label, uncertain=score.uncertain,
            start_seconds=annotation.start_seconds, end_seconds=annotation.end_seconds,
            score_frequency_hz=annotation.frequency_hz, interior_frames=int(inside.sum()),
            raw_f0_coverage=float(raw_valid.sum()/inside.sum()) if inside.any() else None,
            accepted_f0_coverage=float(valid.sum()/inside.sum()) if inside.any() else None,
            raw_within_100c_fraction=float(np.mean(abs(raw_cents) <= 100)) if len(raw_cents) else None,
            accepted_median_delta_cents=float(np.median(cents)) if len(cents) else None,
            overlapping_event_count=len(overlapping),
            overlapping_events=[dict(start=n.start_seconds,end=n.end_seconds,note=n.nearest_note) for n in overlapping]))
    rests = []
    for rest, (a, b) in zip(reference.rests, rest_spans):
        inside = (times >= a) & (times < b)
        rests.append(dict(label=rest.label, start_seconds=a, end_seconds=b,
                          accepted_f0_fraction=float(np.mean(np.isfinite(accepted[inside]))) if inside.any() else None,
                          interpretation='Presence during a score rest is not a false-positive verdict: verify sustain, ornament, reverb or accompaniment against audio.'))
    return {'reference_status':reference.status, 'interpretation':'Score proximity and gaps only; neither frame pitch accuracy nor note F1. Timing/register and performance deviations are not ground truth.',
            'comparison_policy':reference.comparison_policy, 'score_rests':rests,
            'scope_seconds':[start,end], 'config':result.run.config.model_dump(),
            'raw_f0_coverage':float(np.mean(np.isfinite(raw[scope]))),
            'accepted_f0_coverage':float(np.mean(np.isfinite(accepted[scope]))),
            'rows':rows}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--result',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    reference=ScoreReference.model_validate_json(args.reference.read_text())
    result=RecognitionResult.model_validate_json(args.result.read_text())
    report=compare(result,reference)
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    (args.output/'score.annotations.json').write_text(json.dumps([a.model_dump() for a in reference.annotations()],ensure_ascii=False,indent=2))
    with (args.output/'comparison.csv').open('w',newline='') as stream:
        columns=[k for k in report['rows'][0] if k!='overlapping_events']
        writer=csv.DictWriter(stream,fieldnames=columns,extrasaction='ignore')
        writer.writeheader();writer.writerows(report['rows'])
    print(json.dumps({k:v for k,v in report.items() if k!='rows'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
