import ast
from pathlib import Path
import tempfile
import unittest

from app.core.component_version import read_version


class RuntimeTests(unittest.TestCase):
    def test_root_version_matches(self):
        self.assertEqual(read_version(), Path("VERSION").read_text().strip())

    def test_invalid_and_missing_version_fail(self):
        root = Path(".version-tests")
        root.mkdir(exist_ok=True)
        source = Path(tempfile.mkdtemp(dir=root)) / "VERSION"
        with self.assertRaises(FileNotFoundError):
            read_version(source)
        for value in ("", "1.0.0a", "1.0.0-beta", "garbage"):
            source.write_text(value)
            with self.assertRaises(ValueError):
                read_version(source)

    def test_fastapi_uses_reader(self):
        tree = ast.parse(Path("app/main.py").read_text())
        constructors = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                        and isinstance(n.func, ast.Name) and n.func.id == "FastAPI"]
        self.assertEqual(len(constructors), 1)
        value = next(k.value for k in constructors[0].keywords if k.arg == "version")
        self.assertIsInstance(value, ast.Call)
        self.assertEqual(value.func.id, "read_version")


if __name__ == "__main__":
    unittest.main()
