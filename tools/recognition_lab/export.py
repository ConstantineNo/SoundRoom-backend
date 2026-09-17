"""Explicit result exports never embed or copy source audio."""
import csv
from pathlib import Path
from app.schemas.audio_recognition import RecognitionResult, PitchFrame, NoteEvent


def export_result(result: RecognitionResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    for name in ("frames", "notes"):
        rows = [item.model_dump() for item in getattr(result, name)]
        with path.with_suffix(f".{name}.csv").open("w", newline="", encoding="utf-8") as output:
            fields = list((PitchFrame if name == "frames" else NoteEvent).model_fields)
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    path.with_suffix(".params.json").write_text(result.run.config.model_dump_json(indent=2), encoding="utf-8")
