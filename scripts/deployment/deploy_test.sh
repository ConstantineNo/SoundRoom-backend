#!/usr/bin/env bash
# Local entry point. Run only after verifying the target host/SSH port.
set -euo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
server=${1:?usage: deploy_test.sh SERVER USER KEY [SSH_PORT]}
ssh_user=${2:?missing SSH user}
key_file=${3:?missing private key path}
ssh_port=${4:-22}
[[ "$server" =~ ^[a-zA-Z0-9.-]+$ && "$ssh_user" =~ ^[a-zA-Z0-9_-]+$ && "$ssh_port" =~ ^[0-9]+$ ]] || exit 2
cd "$repo"
mkdir -p .runtime/deployment
python3 scripts/deployment/package.py > .runtime/deployment/latest-package.json
archive=$(python3 -c 'import json;print(json.load(open(".runtime/deployment/latest-package.json"))["archive"])')
release=$(python3 -c 'import json;print(json.load(open(".runtime/deployment/latest-package.json"))["release"])')
sha=$(python3 -c 'import json;print(json.load(open(".runtime/deployment/latest-package.json"))["sha256"])')
ssh_args=(-i "$key_file" -p "$ssh_port" -o BatchMode=yes -o ConnectTimeout=20 -o ServerAliveInterval=10 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=accept-new -o "UserKnownHostsFile=$repo/.runtime/deployment/known_hosts")
target="$ssh_user@$server"
# The upload/release directories are permanent parts of the service workspace.
ssh "${ssh_args[@]}" "$target" "sudo install -d -o '$ssh_user' -g '$ssh_user' -m 0755 /opt/soundroom/incoming /opt/soundroom/releases"
ssh "${ssh_args[@]}" "$target" "cat > '/opt/soundroom/incoming/$release.tar.gz'" < "$archive"
ssh "${ssh_args[@]}" "$target" "echo '$sha  /opt/soundroom/incoming/$release.tar.gz' | sha256sum -c - && mkdir '/opt/soundroom/releases/$release' && tar -xzf '/opt/soundroom/incoming/$release.tar.gz' -C '/opt/soundroom/releases/$release' && sudo systemd-run --no-block --unit='soundroom-deploy-$release' --property=Type=oneshot --property=RemainAfterExit=yes /usr/bin/bash '/opt/soundroom/releases/$release/scripts/deployment/install_server.sh' '$server'"
printf 'Deployment scheduled for release: %s\nInspect systemd deployment task before considering it complete.\nExpected URL (verify externally): http://%s\n' "$release" "$server"
