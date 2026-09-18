"""The root VERSION is the sole backend component version source."""
from pathlib import Path
import re


def read_version(path: Path = Path(__file__).resolve().parents[2] / "VERSION") -> str:
    value = path.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)[b-z]?", value):
        raise ValueError(f"Invalid backend component VERSION: {value!r}")
    return value


if __name__ == "__main__":
    print(read_version())
