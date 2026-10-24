#!/usr/bin/env bash
# (Re)creates this project's own n8n at http://localhost:5679. Data (workflows, credentials) lives in the
# docker volume brightpan-invoice-n8n-data, so re-running this keeps everything.
# Only the variables the workflows need are passed from .env; run.sh never passes the Anthropic key or database URL.
# They go in through a temporary --env-file, not the command line, so they don't show up in `ps`.
set -euo pipefail
cd "$(dirname "$0")/.."

envfile=$(mktemp)
chmod 600 "$envfile"
trap 'rm -f "$envfile"' EXIT
python3 - "$envfile" <<'PY'
import sys
from pathlib import Path

values = {}
for line in Path(".env").read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.removeprefix("export ").split("=", 1)
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]  # same as python-dotenv, so n8n and the API see the same token
    values[key.strip()] = value
keep = ["SLACK_WEBHOOK_URL", "AP_REGISTER_SHEET_URL", "GMAIL_INTAKE_ADDRESS", "API_TOKEN"]
fixed = {
    "N8N_EDITOR_BASE_URL": "http://localhost:5679",
    "WEBHOOK_URL": "http://localhost:5679/",
    "GENERIC_TIMEZONE": "America/New_York",
    "TZ": "America/New_York",
    "N8N_BLOCK_ENV_ACCESS_IN_NODE": "false",
    "N8N_DIAGNOSTICS_ENABLED": "false",
    "N8N_RESTRICT_FILE_ACCESS_TO": "/samples",
    "API_URL_FOR_N8N": "http://host.docker.internal:8040",
}
lines = [f"{k}={v}" for k, v in fixed.items()] + [f"{k}={values.get(k, '')}" for k in keep]
Path(sys.argv[1]).write_text("\n".join(lines) + "\n")
PY

docker rm -f brightpan-invoice-n8n >/dev/null 2>&1 || true
docker run -d --name brightpan-invoice-n8n --restart unless-stopped \
  -p 127.0.0.1:5679:5678 \
  -v brightpan-invoice-n8n-data:/home/node/.n8n \
  -v "$PWD/n8n:/workflows:ro" \
  -v "$PWD/samples:/samples:ro" \
  --env-file "$envfile" \
  docker.n8n.io/n8nio/n8n:2.43.7 >/dev/null
echo "n8n starting at http://localhost:5679"
