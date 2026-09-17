"""Independent test tree: fail hard if anything tries to import business persistence."""
import importlib.abc
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.recognition_lab.runtime import configure_runtime
configure_runtime()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class RejectBusinessImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "app.main" or fullname.startswith(("app.core.database", "app.models", "app.crud", "sqlalchemy")):
            raise AssertionError(f"Isolated recognition must not import {fullname}")
        return None


sys.meta_path.insert(0, RejectBusinessImports())
