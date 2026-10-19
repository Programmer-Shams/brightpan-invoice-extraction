#!/usr/bin/env bash
# Imports the Demo 4 workflows into Demo 4's n8n, attaches the credentials that exist there (looked up by type,
# so the repo files stay instance-independent), publishes the ones that run on their own, and restarts n8n.
set -euo pipefail
cd "$(dirname "$0")/.."
C=brightpan-invoice-n8n

creds=$(docker exec "$C" sh -c 'n8n export:credentials --all --output=/tmp/c.json >/dev/null 2>&1 || echo "[]" > /tmp/c.json
node -e "for (const c of require(\"/tmp/c.json\")) console.log(c.type+\"\t\"+c.id+\"\t\"+c.name)"; rm -f /tmp/c.json')

python3 - "$creds" <<'PY'
import json, sys
creds = {}
for line in sys.argv[1].splitlines():
    t, cid, name = line.split("\t")
    creds.setdefault(t, {"id": cid, "name": name})
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
    runs_alone = any(n["type"] in ("n8n-nodes-base.webhook", "n8n-nodes-base.gmailTrigger") for n in wf["nodes"])
    status = f"missing credential {', '.join(sorted(set(missing)))}" if missing else "ok"
    print(f"{f}: {status}", file=sys.stderr)
    if runs_alone and not missing:
        publish.append(wf["id"])
open("/tmp/brightpan-publish.txt", "w").write("\n".join(publish))
PY

for f in ap-outputs gmail-intake send-test-emails; do
  docker cp "/tmp/brightpan-$f.json" "$C:/tmp/$f.json" && rm -f "/tmp/brightpan-$f.json"
  docker exec "$C" n8n import:workflow --input="/tmp/$f.json" 2>&1 | grep -qi "imported" && echo "imported $f"
done
while read -r id || [ -n "$id" ]; do  # the last line has no newline
  [ -n "$id" ] && docker exec -e N8N_RUNNERS_BROKER_PORT=5690 "$C" n8n publish:workflow --id="$id" >/dev/null 2>&1 && echo "published $id"
done < /tmp/brightpan-publish.txt
rm -f /tmp/brightpan-publish.txt
./n8n/run.sh
