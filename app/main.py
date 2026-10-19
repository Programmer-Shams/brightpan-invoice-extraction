"""Extraction API.  uv run uvicorn app.main:app --port 8040"""
import csv
import hmac
import io
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import quote
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from eval.scoring import HEADER_FIELDS, compute_metrics

from . import config, db, notify, worker
from .extract import ExtractionError, render_pdf_pages

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
MAX_BYTES = 20 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    stop = worker.start_in_background() if os.getenv("RUN_WORKER", "1") == "1" else None
    yield
    if stop:
        stop.set()
    db.pool.close()


def require_token(request: Request) -> None:
    if request.url.path == "/health":
        return
    if not config.API_TOKEN:
        raise HTTPException(503, "API_TOKEN is not configured")
    sent = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(sent.encode(), config.API_TOKEN.encode()):
        raise HTTPException(401, "missing or invalid API token")


# The interactive docs and OpenAPI schema are off: app-level dependencies don't cover them, and the API is token-only.
app = FastAPI(title="Brightpan invoice extraction API", lifespan=lifespan, dependencies=[Depends(require_token)],
              docs_url=None, redoc_url=None, openapi_url=None)


def sniff(data: bytes) -> str | None:
    """The file's own bytes decide its type; the declared content type is never trusted."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return None


@app.post("/documents", status_code=202)
async def upload(file: UploadFile = File(...), source: Literal["upload", "email", "eval"] = Form("upload")):
    data = await file.read(MAX_BYTES + 1)
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(413 if data else 400, "file is empty or larger than 20 MB")
    content_type = sniff(data)
    if content_type is None:
        raise HTTPException(415, "only PDF, JPEG and PNG are accepted")
    row = db.insert_document(file.filename or "upload", content_type, data, source)
    return {"id": str(row["id"]), "status": row["status"]}


def valid_id(document_id: str) -> str:
    try:
        return str(uuid.UUID(document_id))
    except ValueError:
        raise HTTPException(404, "document not found")


def seconds(row: dict) -> float | None:
    s = row["processing_seconds"]
    return float(s) if s is not None and row["status"] in ("done", "failed") else None


def summary(row: dict) -> dict:
    return {
        "id": str(row["id"]), "filename": row["filename"], "content_type": row["content_type"],
        "source": row["source"], "status": row["status"], "pages": row["pages"], "error": row["error"],
        "received_at": row["received_at"], "processing_seconds": seconds(row),
        "vendor_name": row["vendor_name"], "invoice_number": row["invoice_number"], "currency": row["currency"],
        "total": float(row["total"]) if row["total"] is not None else None, "route": row["route"],
        "flags": row["flags"] or [], "review_status": row["review_status"], "outputs_status": row["outputs_status"],
        "cost_usd": float(row["cost_usd"]) if row["cost_usd"] is not None else None,
    }


@app.get("/documents")
def list_documents(limit: int = 100, include_eval: bool = False):
    return [summary(r) for r in db.list_documents(min(max(limit, 1), 500), include_eval)]


@app.get("/documents/{document_id}")
def get_document(document_id: str):
    row = db.get_document(valid_id(document_id))
    if row is None:
        raise HTTPException(404, "document not found")
    return {
        "id": str(row["id"]), "filename": row["filename"], "content_type": row["content_type"],
        "source": row["source"], "status": row["status"], "pages": row["pages"], "error": row["error"],
        "received_at": row["received_at"], "finished_at": row["finished_at"],
        "processing_seconds": seconds(row),
        "record": row["record"], "input_mode": row["input_mode"], "outputs_status": row["outputs_status"],
        "outputs_gave_up": (row["outputs_attempts"] or 0) >= db.MAX_OUTPUT_ATTEMPTS and row["outputs_status"] != "sent",
        "review": {"status": row["review_status"], "note": row["reviewer_note"]} if row["review_status"] else None,
        "usage": usage(row),
    }


def usage(row: dict) -> dict:
    """Token use of the stored extraction, or of the failed calls when there is none."""
    if row["model"] is not None:
        return {"model": row["model"], "input_tokens": row["input_tokens"], "output_tokens": row["output_tokens"],
                "cost_usd": float(row["cost_usd"]) if row["cost_usd"] is not None else None}
    f = row["failure_usage"] or {}
    return {"model": f.get("model"), "input_tokens": f.get("input_tokens"), "output_tokens": f.get("output_tokens"),
            "cost_usd": f.get("cost_usd")}


def content_disposition(filename: str) -> str:
    """RFC 6266: an ASCII fallback plus the UTF-8 name, so any filename (€, 发票, quotes) is safe in the header."""
    ascii_name = "".join(c if 32 <= ord(c) < 127 and c not in '"\\' else "_" for c in filename) or "document"
    return f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"


@app.get("/documents/{document_id}/file")
def get_file(document_id: str):
    row = db.get_file(valid_id(document_id))
    if row is None:
        raise HTTPException(404, "document not found")
    return Response(bytes(row["file_bytes"]), media_type=row["content_type"],
                    # Only byte-checked PDF/JPEG/PNG are stored, and nosniff stops a browser treating them as
                    # anything else. (No CSP sandbox: Chrome refuses to open its PDF viewer under one.)
                    headers={"Content-Disposition": content_disposition(row["filename"]),
                             "X-Content-Type-Options": "nosniff"})


PREVIEW_DPI = 110


@app.get("/documents/{document_id}/pages/{page}")
def page_image(document_id: str, page: int):
    """One page of a PDF as PNG, so every browser shows the original the same way beside the fields."""
    row = db.get_file(valid_id(document_id))
    if row is None:
        raise HTTPException(404, "document not found")
    if row["content_type"] != "application/pdf":
        raise HTTPException(400, "only PDFs have page images; use /file for images")
    try:
        [image] = render_pdf_pages(bytes(row["file_bytes"]), PREVIEW_DPI, pages=[page - 1])
    except IndexError:
        raise HTTPException(404, "page not found")
    except ExtractionError as e:
        raise HTTPException(422, str(e))
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/review")
def list_review(status: Literal["open", "approved", "rejected"] = "open", include_eval: bool = False):
    return [summary(r) | {"review_reasons": r["review_reasons"]} for r in db.list_review(status, include_eval)]


class ReviewDecision(BaseModel):
    action: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=1000)


@app.post("/review/{document_id}")
def resolve_review(document_id: str, decision: ReviewDecision):
    """Approve sends the record to the AP register; reject keeps it out of the books."""
    status = "approved" if decision.action == "approve" else "rejected"
    row = db.resolve_review(valid_id(document_id), status, decision.note)
    if row is None:
        raise HTTPException(409, "no open review item for this document")
    outputs = None
    if status == "approved":
        outputs = notify.send(row, row["record"], event="review.approved")
        db.set_outputs_status(row["id"], outputs)
    return {"id": str(row["id"]), "review_status": status, "outputs_status": outputs}


@app.get("/results")
def eval_results():
    """The latest eval run, straight from eval/results.csv (every number on the results page comes from it)."""
    path = config.ROOT / "eval" / "results.csv"
    if not path.exists():
        raise HTTPException(404, "no eval run yet: run eval/run_eval.py")
    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    docs: dict[str, dict] = {}
    for r in rows:
        d = docs.setdefault(r["document_id"], {"document_id": r["document_id"], "format": r["format"],
                                               "header_correct": 0, "header_total": 0, "lines_correct": 0,
                                               "lines_total": 0, "mismatches": []})
        if r["kind"] in ("header", "line_item"):
            key = "header" if r["kind"] == "header" else "lines"
            d[f"{key}_total"] += 1
            d[f"{key}_correct"] += r["match"] == "1"
            if r["match"] != "1":
                d["mismatches"].append({"field": r["field"], "expected": r["expected"], "actual": r["actual"]})
        elif r["kind"] in ("route", "flags"):
            d[f"{r['kind']}_expected"], d[f"{r['kind']}_actual"] = r["expected"], r["actual"]
        elif r["kind"] == "meta":
            d[r["field"]] = r["actual"]
    return {"metrics": compute_metrics(rows), "header_fields": HEADER_FIELDS, "documents": list(docs.values()),
            "run_at": run_time(rows)}


def run_time(rows: list[dict]) -> str | None:
    """When the eval ran: the run_id it recorded (e.g. 20261019T195036Z), else the newest eval/runs folder."""
    run_id = next((r["actual"] for r in rows if r["kind"] == "meta" and r["field"] == "run_id"), None)
    if run_id is None:
        runs = sorted(p.name for p in (config.ROOT / "eval" / "runs").glob("*T*Z") if p.is_dir())
        run_id = runs[-1] if runs else None
    try:
        return datetime.strptime(run_id, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).isoformat() if run_id else None
    except ValueError:
        return None


@app.get("/health")
def health():
    """Open (no token), so it says only whether the parts are up."""
    status = {"database": db.ping(), "worker": worker.health()}
    expected_worker = os.getenv("RUN_WORKER", "1") == "1"
    ok = status["database"] and (status["worker"]["running"] or not expected_worker)
    return JSONResponse({"ok": ok, **status}, status_code=200 if ok else 503)


@app.post("/admin/reset")
def reset():
    if not config.ALLOW_RESET:
        raise HTTPException(403, "reset is disabled (set ALLOW_RESET=1 for local eval runs)")
    return {"ok": True, "deleted_eval_documents": db.reset_eval()}
