"""Keep runtime caches and temporary data inside the repository."""
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def configure_runtime() -> Path:
    runtime = ROOT / ".runtime"
    for name in ("tmp", "cache", "numba", "config", "data"):
        (runtime / name).mkdir(parents=True, exist_ok=True)
    for key, name in {"TMPDIR": "tmp", "TEMP": "tmp", "TMP": "tmp", "XDG_CACHE_HOME": "cache",
                      "NUMBA_CACHE_DIR": "numba", "MPLCONFIGDIR": "config",
                      "XDG_CONFIG_HOME": "config", "XDG_DATA_HOME": "data"}.items():
        os.environ[key] = str(runtime / name)
    tempfile.tempdir = str(runtime / "tmp")
    return runtime
