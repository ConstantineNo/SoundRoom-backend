"""One cold-cache pYIN analysis followed by the identical warmed run."""
from .runtime import configure_runtime
runtime = configure_runtime()
import argparse
import json
import os
from pathlib import Path
import platform
import resource
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cache = runtime / 'numba' / f'benchmark-{time.time_ns()}'
    cache.mkdir(parents=True)
    os.environ['NUMBA_CACHE_DIR'] = str(cache)
    from app.services.audio_recognition import analyze, from_pcm
    from .synthetic import cases
    case = cases()[0]
    audio = from_pcm(case.samples, case.sample_rate)
    results = []
    for label in ('fresh_process_empty_numba_cache', 'same_process_warm'):
        start = time.perf_counter()
        result = analyze(audio)
        results.append({'condition': label, 'wall_seconds': time.perf_counter() - start,
                        'run': result.run.model_dump(), 'notes': len(result.notes)})
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report = {'hardware': {'platform': platform.platform(), 'machine': platform.machine(),
                           'processor': platform.processor(), 'python': platform.python_version(), 'cpu_count': os.cpu_count()},
              'audio_seconds': audio.info.duration_seconds, 'input_sample_rate': audio.info.sample_rate,
              'source': case.name, 'runs': results,
              'process_peak_rss_mib': peak / (1024 ** 2 if platform.system() == 'Darwin' else 1024),
              'memory_semantics': 'process-lifetime high-water RSS; includes both analyses and imports',
              'cold_semantics': 'fresh process and empty Numba cache; OS disk caches not flushed; package imports excluded from analysis wall time'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
