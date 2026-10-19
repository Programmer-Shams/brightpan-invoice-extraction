"""Eval harness: uploads every sample to the API, polls until done, scores against truth/,
writes eval/results.csv and prints the BUILD_SPEC metrics.

  uv run python eval/run_eval.py                       # all 20 samples against http://localhost:8040
  uv run python eval/run_eval.py --only INV10 INV16    # a subset
  uv run python eval/run_eval.py --from-csv eval/results.csv   # recompute metrics, no API calls

Documents are uploaded one at a time in manifest order (INV01 before INV16, so the duplicate
check sees the original first) and each is timed from upload to finished.
"""
import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import dotenv_values
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scoring import CSV_COLUMNS, compute_metrics, score_document  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MIME = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def page_count(path: Path) -> int:
    return len(PdfReader(path).pages) if path.suffix.lower() == ".pdf" else 1


def run_one(client: httpx.Client, path: Path, timeout: float, poll: float) -> dict:
    """Uploads one file and polls until it finishes. Never raises for an API problem: the outcome is recorded
    in the returned body (status upload_failed / poll_failed / timeout) and scored as a miss."""
    started = time.monotonic()
    body: dict = {}
    try:
        with path.open("rb") as fh:
            r = client.post("/documents", files={"file": (path.name, fh, MIME[path.suffix.lower()])},
                            data={"source": "eval"})
        if r.status_code != 202:
            body = {"status": "upload_failed", "error": f"HTTP {r.status_code}: {r.text[:200]}"}
        else:
            doc_id = r.json()["id"]
            while True:
                g = client.get(f"/documents/{doc_id}")
                if g.status_code != 200:
                    body = {"status": "poll_failed", "error": f"HTTP {g.status_code}: {g.text[:200]}"}
                    break
                try:
                    body = g.json()
                except ValueError:
                    body = {"status": "poll_failed", "error": f"non-JSON response: {g.text[:200]}"}
                    break
                if body.get("status") in ("done", "failed"):
                    break
                if time.monotonic() - started > timeout:
                    body["status"] = "timeout"
                    break
                time.sleep(poll)
    except httpx.HTTPError as e:
        body = {"status": "request_failed", "error": f"{type(e).__name__}: {e}"}
    client_seconds = time.monotonic() - started
    if body.get("processing_seconds") is None:
        body["processing_seconds"] = round(client_seconds, 3)
        body["seconds_source"] = "client"
    else:
        body["seconds_source"] = "server"
    return body


def print_metrics(m: dict) -> None:
    print("\n=== Demo 4 eval metrics (measured) ===")
    print(f"Documents finished:   {m['documents_done']}/{m['documents']}"
          + (f"  not done: {', '.join(m['documents_not_done'])}" if m["documents_not_done"] else ""))
    print(f"Field accuracy:       {m['field_accuracy']}")
    for k, v in m["field_accuracy_by_format"].items():
        print(f"  {k:<10}          {v}")
    print("  by field:")
    for k, v in m["field_accuracy_by_field"].items():
        print(f"    {k:<16}  {v}")
    print(f"Line-item accuracy:   {m['line_item_accuracy']}   (extra extracted lines: {m['extra_line_items']})")
    print(f"Planted to review:    {m['planted_caught']}   correct flag: {m['planted_flag_correct']}")
    print(f"False reviews:        {m['false_reviews']}")
    print(f"Invented values:      {m['invented_values']}" + (f"  {m['invented_detail']}" if m["invented_detail"] else ""))
    print(f"Seconds per doc:      median {m['seconds_per_doc_median']}  max {m['seconds_per_doc_max']}")
    print(f"Pages per minute:     {m['pages_per_minute']}")
    print(f"Cost per doc (USD):   mean {m['cost_per_doc_mean_usd']}  max {m['cost_per_doc_max_usd']}  total {m['cost_total_usd']}")
    print(f"Tokens:               in {m['input_tokens_total']}  out {m['output_tokens_total']}  models {m['models']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8040")
    ap.add_argument("--only", nargs="*", help="document ids to run (default: all in manifest)")
    ap.add_argument("--timeout", type=float, default=300, help="seconds per document")
    ap.add_argument("--poll", type=float, default=0.5)
    ap.add_argument("--no-reset", action="store_true", help="do not call POST /admin/reset first")
    ap.add_argument("--out", default=str(ROOT / "eval" / "results.csv"))
    ap.add_argument("--from-csv", help="recompute metrics from an existing results.csv")
    args = ap.parse_args()

    if args.from_csv:
        with open(args.from_csv, newline="") as fh:
            print_metrics(compute_metrics(list(csv.DictReader(fh))))
        return

    with open(ROOT / "truth" / "manifest.csv", newline="") as fh:
        manifest = list(csv.DictReader(fh))
    if args.only:
        manifest = [m for m in manifest if m["document_id"] in set(args.only)]

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_dir = ROOT / "eval" / "runs" / run_id
    raw_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    out, partial = Path(args.out), Path(args.out + ".partial")
    fh = partial.open("w", newline="")  # written as each document finishes; replaces results.csv only when complete
    writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    token = dotenv_values(ROOT / ".env").get("API_TOKEN") or ""
    with httpx.Client(base_url=args.api, timeout=60, headers={"Authorization": f"Bearer {token}"}) as client:
        if not args.no_reset:
            r = client.post("/admin/reset")
            if r.status_code != 200:
                sys.exit(f"reset failed (HTTP {r.status_code}: {r.text[:200]}); a stale database would flag "
                         "re-uploaded samples as duplicates. Start the API with ALLOW_RESET=1 or pass --no-reset.")
            print("reset: ok")
        for m in manifest:
            path = ROOT / "samples" / m["file"]
            truth = json.loads((ROOT / "truth" / f"{m['document_id']}.json").read_text())
            body = run_one(client, path, args.timeout, args.poll)
            body["pages"] = page_count(path)  # property of the file, not of the extractor
            (raw_dir / f"{m['document_id']}.json").write_text(json.dumps(body, indent=2))
            doc_rows = score_document(truth, body)
            doc_rows.append({"document_id": m["document_id"], "format": truth["format"], "kind": "meta",
                             "field": "run_id", "expected": "", "actual": run_id, "match": "", "invented": ""})
            rows.extend(doc_rows)
            writer.writerows(doc_rows)
            fh.flush()
            hdr = [r for r in doc_rows if r["kind"] == "header"]
            print(f"{m['document_id']:<7} {body.get('status'):<9} {body['processing_seconds']:>7.2f}s "
                  f"fields {sum(int(r['match']) for r in hdr)}/{len(hdr)}  route={(body.get('record') or {}).get('route')}")

    fh.close()
    partial.replace(out)
    print(f"\nwrote {out} ({len(rows)} rows); raw responses in {raw_dir.relative_to(ROOT)}/")
    print_metrics(compute_metrics(rows))


if __name__ == "__main__":
    main()
