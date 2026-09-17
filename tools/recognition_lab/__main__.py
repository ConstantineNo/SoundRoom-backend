import argparse
from pathlib import Path
from .runtime import configure_runtime


def main():
    configure_runtime()
    from PySide6.QtWidgets import QApplication
    from .gui import RecognitionWindow
    parser = argparse.ArgumentParser(description="SoundRoom local recognition lab")
    parser.add_argument("input", type=Path, nargs="?")
    args = parser.parse_args()
    app = QApplication([])
    window = RecognitionWindow()
    window.show()
    if args.input:
        window.import_file(args.input)
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
