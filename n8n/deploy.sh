#!/usr/bin/env bash
# Imports n8n/ap-outputs.workflow.json into Demo 4's n8n, attaches the Google Sheets credential that exists
# there (looked up by type, so the repo file stays instance-independent), publishes it and restarts n8n.
set -euo pipefail
cd "$(dirname "$0")/.."
C=brightpan-invoice-n8n
cred=$(docker exec "$C" sh -c 'n8n export:credentials --all --output=/tmp/c.json >/dev/null 2>&1; node -e "
const c=require(\"/tmp/c.json\").find(c=>c.type===\"googleSheetsOAuth2Api\"); if(c) console.log(c.id+\"\t\"+c.name)"; rm -f /tmp/c.json')
[ -n "$cred" ] || { echo "no Google Sheets credential in n8n yet (create it at http://localhost:5679)"; exit 1; }
python3 - "$cred" <<'PY'
import json, sys
cid, name = sys.argv[1].split("\t")
wf = json.load(open("n8n/ap-outputs.workflow.json"))
for n in wf["nodes"]:
    if n["type"] == "n8n-nodes-base.googleSheets":
        n["credentials"] = {"googleSheetsOAuth2Api": {"id": cid, "name": name}}
json.dump(wf, open("/tmp/brightpan-ap-outputs.json", "w"))
PY
docker cp /tmp/brightpan-ap-outputs.json "$C":/tmp/ap-outputs.json && rm -f /tmp/brightpan-ap-outputs.json
docker exec "$C" n8n import:workflow --input=/tmp/ap-outputs.json 2>&1 | grep -i "imported"
docker exec -e N8N_RUNNERS_BROKER_PORT=5690 "$C" n8n publish:workflow --id=njHZvEemZ1jo9e2U 2>&1 | grep -i "publishing"
./n8n/run.sh
