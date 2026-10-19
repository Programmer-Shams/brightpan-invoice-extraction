#!/usr/bin/env bash
# (Re)creates Demo 4's own n8n at http://localhost:5679. Data (workflows, credentials) lives in the
# docker volume brightpan-invoice-n8n-data, so re-running this keeps everything.
# Only the variables the workflows need are read from .env; the Anthropic key and database URL never reach n8n.
set -euo pipefail
cd "$(dirname "$0")/.."

env_value() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- || true; }

docker rm -f brightpan-invoice-n8n >/dev/null 2>&1 || true
docker run -d --name brightpan-invoice-n8n --restart unless-stopped \
  -p 127.0.0.1:5679:5678 \
  -v brightpan-invoice-n8n-data:/home/node/.n8n \
  -v "$PWD/n8n:/workflows:ro" \
  -v "$PWD/samples:/samples:ro" \
  -e N8N_RESTRICT_FILE_ACCESS_TO=/samples \
  -e N8N_EDITOR_BASE_URL=http://localhost:5679 \
  -e WEBHOOK_URL=http://localhost:5679/ \
  -e GENERIC_TIMEZONE=America/New_York -e TZ=America/New_York \
  -e N8N_BLOCK_ENV_ACCESS_IN_NODE=false \
  -e N8N_DIAGNOSTICS_ENABLED=false \
  -e SLACK_WEBHOOK_URL="$(env_value SLACK_WEBHOOK_URL)" \
  -e AP_REGISTER_SHEET_URL="$(env_value AP_REGISTER_SHEET_URL)" \
  -e GMAIL_INTAKE_ADDRESS="$(env_value GMAIL_INTAKE_ADDRESS)" \
  -e API_TOKEN="$(env_value API_TOKEN)" \
  -e API_URL_FOR_N8N=http://host.docker.internal:8040 \
  docker.n8n.io/n8nio/n8n:2.43.7 >/dev/null
echo "n8n starting at http://localhost:5679"
