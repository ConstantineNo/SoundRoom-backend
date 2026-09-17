"""Reproducible synthetic and annotation metrics; tolerances are evaluation definitions."""
from .runtime import configure_runtime
configure_runtime()
import argparse
import json
import platform
from pathlib import Path
import resource
import time
import numpy as np
from scipy.optimize import linear_sum_assignment
from pydantic import TypeAdapter
from app.schemas.audio_recognition import Annotation, RecognitionConfig
from app.services.audio_recognition import analyze, from_pcm, load_audio
from .synthetic import cases, write_case
from .export import export_result


def note_metrics(predicted, truth, seconds=.1, cents=50):
    cost = np.full((len(truth), len(predicted)), 1e6)
    for i, expected in enumerate(truth):
        for j, found in enumerate(predicted):
            onset = abs(expected.start_seconds - found.start_seconds)
            offset = abs(expected.end_seconds - found.end_seconds)
            pitch = abs(1200 * np.log2(found.frequency_hz / expected.frequency_hz))
            if onset <= seconds and offset <= seconds and pitch <= cents:
                cost[i, j] = onset + offset + pitch / 1200
    rows, cols = linear_sum_assignment(cost)
    pairs = [(int(i), int(j)) for i, j in zip(rows, cols) if cost[i, j] < 1e6]
    matched = len(pairs)
    precision = matched / len(predicted) if predicted else (1. if not truth else 0.)
    recall = matched / len(truth) if truth else (1. if not predicted else 0.)
    return dict(tolerance_seconds=seconds, tolerance_cents=cents, expected=len(truth), predicted=len(predicted), matched=matched,
                precision=precision, recall=recall, f1=2 * precision * recall / (precision + recall) if precision + recall else 0.,
                onset_errors_seconds=[predicted[j].start_seconds - truth[i].start_seconds for i, j in pairs],
                offset_errors_seconds=[predicted[j].end_seconds - truth[i].end_seconds for i, j in pairs])


def synthetic_report(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    config = RecognitionConfig()
    report = {"evidence_kind": "synthetic mechanisms only; not real instrument/voice acceptance",
              "hardware": {"platform": platform.platform(), "machine": platform.machine(), "python": platform.python_version()},
              "config": config.model_dump(), "cases": [], "checks": {}}
    for index, case in enumerate(cases()):
        path = write_case(case, directory / "fixtures")
        start = time.perf_counter()
        result = analyze(load_audio(path), config)
        wall = time.perf_counter() - start
        samples = np.array([f.source_sample for f in result.frames])
        actual = np.array([f.f0_hz if f.voiced else np.nan for f in result.frames])
        expected = case.expected_hz[samples]
        # Exclude 60 ms around note edges from pitch statistics (also report voicing over all frames).
        interior = np.isfinite(expected)
        times = np.array([f.time_seconds for f in result.frames])
        for note in case.notes:
            interior &= (np.abs(times - note.start_seconds) > .06) & (np.abs(times - note.end_seconds) > .06)
        both = interior & np.isfinite(actual)
        errors = 1200 * np.log2(actual[both] / expected[both])
        reference_voiced = np.isfinite(expected)
        predicted_voiced = np.isfinite(actual)
        # A glide has continuous truth but no single fixed-pitch note annotation.
        metrics = [note_metrics(result.notes, case.notes, tolerance) for tolerance in (.05, .1)] if case.name != "glide" else []
        row = dict(name=case.name, audio_seconds=result.audio.duration_seconds, input_sample_rate=case.sample_rate,
                   elapsed_seconds=result.run.elapsed_seconds, wall_seconds=wall,
                   real_time_factor=result.run.real_time_factor, process_first_analysis=index == 0,
                   absolute_cents_median=float(np.median(np.abs(errors))) if len(errors) else None,
                   absolute_cents_p95=float(np.percentile(np.abs(errors), 95)) if len(errors) else None,
                   octave_error_rate=float(np.mean(np.abs(errors) > 600)) if len(errors) else None,
                   voiced_false_positives=int(np.sum(~reference_voiced & predicted_voiced)),
                   voiced_false_negatives=int(np.sum(reference_voiced & ~predicted_voiced)),
                   interior_voiced_coverage=float(np.mean(predicted_voiced[interior])) if np.any(interior) else None,
                   note_metrics=metrics, note_evaluation_applicable=case.name != "glide",
                   warnings=result.warnings)
        report["cases"].append(row)
        if case.name != "glide":
            report["checks"][f"{case.name}_events_100ms"] = metrics[1]["f1"] == 1
        else:
            report["checks"]["glide_variation_flagged"] = any("variable_pitch_or_glide" in n.flags for n in result.notes)
        if len(errors):
            report["checks"][f"{case.name}_pitch_p95_35c"] = row["absolute_cents_p95"] < 35
            report["checks"][f"{case.name}_voiced_coverage"] = row["interior_voiced_coverage"] > .9
        export_result(result, directory / f"{case.name}.json")
        print(f"{case.name}: {len(result.notes)} notes; p95={row['absolute_cents_p95']}; {wall:.2f}s", flush=True)
    # macOS reports bytes; Linux KiB. This is process-lifetime high-water RSS, not per-call allocation.
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report["process_peak_rss_mib"] = peak / (1024 ** 2 if platform.system() == "Darwin" else 1024)
    report["memory_semantics"] = "process lifetime maximum RSS including imports, JIT and all sequential cases"
    report["all_checks_passed"] = all(report["checks"].values())
    (directory / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--annotations", type=Path)
    args = parser.parse_args()
    if args.audio or args.annotations:
        if not (args.audio and args.annotations):
            parser.error("--audio and --annotations must be provided together")
        truth = TypeAdapter(list[Annotation]).validate_json(args.annotations.read_text())
        result = analyze(load_audio(args.audio))
        if any(a.end_seconds > result.audio.duration_seconds for a in truth):
            parser.error("annotations extend beyond audio")
        args.output.mkdir(parents=True, exist_ok=True)
        export_result(result, args.output / "result.json")
        report = {"evidence_kind": "user supplied audio + discrete note annotations; no continuous F0 accuracy claim",
                  "audio_sha256": result.audio.sha256,
                  "metrics": [note_metrics(result.notes, truth, t) for t in (.05, .1)]}
        (args.output / "report.json").write_text(json.dumps(report, indent=2))
    else:
        report = synthetic_report(args.output)
        raise SystemExit(0 if report["all_checks_passed"] else 1)


if __name__ == "__main__":
    main()
