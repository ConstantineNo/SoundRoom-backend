"""python -m tools.recognition_lab.cli INPUT --output result.json [--params params.json]."""
import argparse
from pathlib import Path
import sys
from .runtime import configure_runtime


def main(argv=None) -> int:
    configure_runtime()
    from app.schemas.audio_recognition import RecognitionConfig
    from app.services.audio_recognition import analyze, load_audio
    from .export import export_result
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--params", type=Path)
    args = parser.parse_args(argv)
    try:
        config = RecognitionConfig.model_validate_json(args.params.read_text()) if args.params else RecognitionConfig()
        result = analyze(load_audio(args.input), config)
        export_result(result, args.output)
    except (ValueError, OSError) as exc:
        print(f"Recognition failed: {exc}", file=sys.stderr)
        return 2
    print(f"{len(result.notes)} note candidates; {result.run.elapsed_seconds:.3f}s; {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
