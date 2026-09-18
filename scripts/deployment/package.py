#!/usr/bin/env python3
"""Create an allowlisted, content-addressed release in the local workspace."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
INCLUDE = ('app', 'migrations', 'classification_tests', 'deploy', 'scripts/deployment',
           'alembic.ini', 'requirements.txt', 'requirements-test.txt')
EXCLUDE = ('app/services/audio_recognition/', 'app/schemas/audio_recognition.py',
           'app/schemas/polyphonic_recognition.py')


def main() -> None:
    files = []
    for name in INCLUDE:
        path = ROOT / name
        for item in (sorted(path.rglob('*')) if path.is_dir() else [path]):
            relative = item.relative_to(ROOT).as_posix()
            if item.is_file() and not item.is_symlink() and '__pycache__' not in item.parts and not relative.startswith(EXCLUDE):
                files.append((relative, item.read_bytes()))
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files}
    fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    release = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + fingerprint[:12]
    manifest = {'release': release, 'source_sha256': fingerprint, 'files': hashes,
                'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'source': 'classification API working-tree snapshot; recognition experiments excluded'}
    output = ROOT / '.runtime' / 'deployment'
    output.mkdir(parents=True, exist_ok=True)
    archive = output / (release + '.tar.gz')
    with tarfile.open(archive, 'w:gz') as tar:
        for name, content in [*files, ('release-manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2).encode())]:
            entry = tarfile.TarInfo(name)
            entry.size = len(content)
            entry.mode = 0o644
            tar.addfile(entry, io.BytesIO(content))
    print(json.dumps({'release': release, 'archive': str(archive), 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
