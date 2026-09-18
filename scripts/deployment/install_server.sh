#!/usr/bin/env bash
# Run from an extracted release as root; permanent data stays outside releases.
set -euo pipefail
umask 0027
release_dir=$(cd "$(dirname "$0")/../.." && pwd)
server_name=${1:?usage: install_server.sh SERVER_NAME}
[[ "$server_name" =~ ^[a-zA-Z0-9.-]+$ ]] || { echo 'Invalid server name' >&2; exit 2; }
[[ "$release_dir" == /opt/soundroom/releases/* ]] || { echo 'Release must be under /opt/soundroom/releases' >&2; exit 2; }
[[ $(id -u) == 0 ]] || { echo 'Run with sudo' >&2; exit 2; }

# Do not change a live service's directory ownership while dependencies install.
for directory in /opt/soundroom/shared /opt/soundroom/shared/tmp; do
    if [[ ! -d "$directory" ]]; then install -d -m 0755 "$directory"; fi
done
install -d -o root -g root -m 0750 /opt/soundroom/incoming/pip-cache
export TMPDIR=/opt/soundroom/shared/tmp
export PIP_CACHE_DIR=/opt/soundroom/incoming/pip-cache
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=l
apt-get update
apt-get install -y python3-venv nginx
id soundroom >/dev/null 2>&1 || useradd --system --home-dir /opt/soundroom/shared --shell /usr/sbin/nologin soundroom
install -d -o soundroom -g soundroom -m 0755 /opt/soundroom/shared
install -d -o soundroom -g soundroom -m 0750 /opt/soundroom/shared/{uploads,private_score_assets,backups,tmp,cache}
install -d -o www-data -g www-data -m 0700 /opt/soundroom/shared/{nginx_body,nginx_proxy}
python3 -m venv "$release_dir/.venv"
"$release_dir/.venv/bin/python" -m pip install -r "$release_dir/requirements.txt" -c "$release_dir/deploy/constraints.txt"
chgrp -R soundroom "$release_dir/.venv"
chmod -R g+rX "$release_dir/.venv"
install -d -o root -g soundroom -m 0750 /etc/soundroom
if [[ ! -f /etc/soundroom/backend.env ]]; then
    python3 - <<'PY'
import os
import secrets
from pathlib import Path
path = Path('/etc/soundroom/backend.env')
with path.open('x') as stream:
    stream.write('DIZI_SECRET_KEY=' + secrets.token_urlsafe(48) + '\n')
    stream.write('DATABASE_URL=sqlite:////opt/soundroom/shared/dizi.db\n')
    stream.write('CLASSIFICATION_ASSET_DIR=/opt/soundroom/shared/private_score_assets\n')
    stream.write('DIZI_DEBUG_ENABLED=false\n')
os.chmod(path, 0o640)
PY
    chown root:soundroom /etc/soundroom/backend.env
fi
# Keep existing configuration and signing key across upgrades.
set -a
source /etc/soundroom/backend.env
set +a
[[ "$DATABASE_URL" == sqlite:////opt/soundroom/shared/dizi.db ]] || { echo 'Unexpected existing DATABASE_URL; review before migration' >&2; exit 3; }
# Stop only the service owned by this deployment before backing up/migrating.
was_active=false
if systemctl is-active --quiet soundroom-backend; then
    was_active=true
    systemctl stop soundroom-backend
fi
report_error() {
    echo "Deployment failed; inspect the service, migration and backup before retrying. No success is claimed." >&2
}
trap report_error ERR
python3 - <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
source = Path('/opt/soundroom/shared/dizi.db')
if source.exists():
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    target = source.parent / 'backups' / ('before-' + timestamp + '.db')
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    print('Database backup:', target)
PY
cd "$release_dir"
"$release_dir/.venv/bin/python" -m alembic upgrade head
chown soundroom:soundroom /opt/soundroom/shared/dizi.db
chmod 0640 /opt/soundroom/shared/dizi.db
# Both the release and the previous target remain available for an explicit rollback.
if [[ -L /opt/soundroom/current ]]; then
    readlink /opt/soundroom/current > /opt/soundroom/shared/previous-release.txt
elif [[ -e /opt/soundroom/current ]]; then
    echo 'Existing current is not a symlink; refusing replacement' >&2
    exit 3
fi
ln -sfn "$release_dir" /opt/soundroom/current
install -m 0644 deploy/soundroom-backend.service /etc/systemd/system/soundroom-backend.service
install -m 0644 deploy/soundroom-proxy.conf /etc/nginx/soundroom-proxy.conf
sed "s/__SERVER_NAME__/$server_name/g" deploy/soundroom-nginx.conf.template > /etc/nginx/sites-available/soundroom-backend.conf
ln -sfn /etc/nginx/sites-available/soundroom-backend.conf /etc/nginx/sites-enabled/soundroom-backend.conf
nginx -t
systemctl daemon-reload
systemctl enable soundroom-backend nginx
systemctl restart soundroom-backend
ready=false
for attempt in {1..20}; do
    if "$release_dir/.venv/bin/python" -c 'import urllib.request,json; r=urllib.request.urlopen("http://127.0.0.1:18080/score-classification-options",timeout=2); assert json.load(r)["code"] == 0' 2>/dev/null; then
        ready=true
        break
    fi
    sleep 1
done
[[ "$ready" == true ]] || { echo 'Backend readiness check failed' >&2; exit 4; }
systemctl reload nginx
trap - ERR
systemctl is-active soundroom-backend nginx
