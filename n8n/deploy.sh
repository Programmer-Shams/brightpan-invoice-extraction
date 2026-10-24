#!/usr/bin/env bash
# Imports the workflows into this project's n8n, attaches the credentials that exist there (looked up by type,
# so the repo files stay instance-independent), publishes the ones that run on their own, and restarts n8n.
# It also (re)creates the outputs webhook's Header Auth credential from OUTPUTS_WEBHOOK_SECRET in .env.
set -euo pipefail
cd "$(dirname "$0")/.."
C=brightpan-invoice-n8n

# 1. Header Auth credential for the outputs webhook. The secret goes in through stdin, never the command line.
uv run python - <<'PY' | docker exec -i "$C" sh -c 'cat > /tmp/cred.json'
import json, sys
from dotenv import dotenv_values
secret = dotenv_values(".env").get("OUTPUTS_WEBHOOK_SECRET") or ""
if not secret:
    sys.exit("OUTPUTS_WEBHOOK_SECRET is missing from .env")
json.dump([{"id": "brightpanOutputsAuth", "name": "Brightpan outputs webhook", "type": "httpHeaderAuth",
            "data": {"name": "X-Brightpan-Signature", "value": secret}}], sys.stdout)
PY
out=$(docker exec "$C" sh -c 'n8n import:credentials --input=/tmp/cred.json 2>&1; rm -f /tmp/cred.json')
echo "$out" | grep -qi "success" || { echo "credential import failed:"; echo "$out" | tail -3; exit 1; }
echo "outputs webhook credential ok"

# 2. Attach credentials by type and decide what may be published.
creds=$(docker exec "$C" sh -c 'n8n export:credentials --all --output=/tmp/c.json >/dev/null 2>&1 || echo "[]" > /tmp/c.json
node -e "for (const c of require(\"/tmp/c.json\")) console.log(c.type+\"\t\"+c.id+\"\t\"+c.name)"; rm -f /tmp/c.json')
intake_address=$(uv run python -c 'from dotenv import dotenv_values; print(dotenv_values(".env").get("GMAIL_INTAKE_ADDRESS") or "")')

python3 - "$creds" "$intake_address" <<'PY'
import json, sys
creds = {}
for line in sys.argv[1].splitlines():
    t, cid, name = line.split("\t")
    creds.setdefault(t, {"id": cid, "name": name})
intake_address = sys.argv[2]
NODE_CRED = {"n8n-nodes-base.googleSheets": "googleSheetsOAuth2Api",
             "n8n-nodes-base.gmail": "gmailOAuth2", "n8n-nodes-base.gmailTrigger": "gmailOAuth2"}
publish = []
for f in ["ap-outputs", "gmail-intake", "send-test-emails"]:
    wf = json.load(open(f"n8n/{f}.workflow.json"))
    missing = []
    for n in wf["nodes"]:
        t = NODE_CRED.get(n["type"])
        if t and t in creds:
            n["credentials"] = {t: creds[t]}
        elif t:
            missing.append(t)
    json.dump(wf, open(f"/tmp/brightpan-{f}.json", "w"))
    uses_intake = any(n["type"] == "n8n-nodes-base.gmailTrigger" for n in wf["nodes"])
    runs_alone = uses_intake or any(n["type"] == "n8n-nodes-base.webhook" for n in wf["nodes"])
    if missing:
        status = f"not published: missing credential {', '.join(sorted(set(missing)))}"
    elif uses_intake and "@" not in intake_address:
        # Without the address the Gmail query would match every email with an attachment.
        status = "not published: GMAIL_INTAKE_ADDRESS is empty"
    elif runs_alone:
        status, _ = "published", publish.append(wf["id"])
    else:
        status = "imported (run by hand)"
    print(f"{f}: {status}", file=sys.stderr)
open("/tmp/brightpan-publish.txt", "w").write("\n".join(publish) + "\n")
PY

# 3. Import, publish, restart.
for f in ap-outputs gmail-intake send-test-emails; do
  docker cp "/tmp/brightpan-$f.json" "$C:/tmp/$f.json" && rm -f "/tmp/brightpan-$f.json"
  out=$(docker exec "$C" n8n import:workflow --input="/tmp/$f.json" 2>&1)
  echo "$out" | grep -qi "successfully imported" || { echo "import of $f failed:"; echo "$out" | tail -3; exit 1; }
done
while read -r id || [ -n "$id" ]; do
  [ -z "$id" ] && continue
  docker exec -e N8N_RUNNERS_BROKER_PORT=5690 "$C" n8n publish:workflow --id="$id" >/dev/null 2>&1 \
    || { echo "publish of $id failed"; exit 1; }
done < /tmp/brightpan-publish.txt
rm -f /tmp/brightpan-publish.txt
./n8n/run.sh
