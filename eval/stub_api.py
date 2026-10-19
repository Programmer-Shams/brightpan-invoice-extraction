"""Null stub of the extraction API, for running the eval harness before the real system exists.

Implements the same contract as the real API:
  POST /documents        multipart `file` (+ optional form `source`) -> 202 {"id", "status"}
  GET  /documents/{id}   -> {"id", "filename", "status", "pages", "received_at", "finished_at",
                             "processing_seconds", "record", "usage", "error"}
  POST /admin/reset      -> clears stored documents (eval runs start clean)

Every field of the record is null, so the eval measures a true zero baseline.
Run: uv run uvicorn eval.stub_api:app --port 8040
"""
import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile

app = FastAPI(title="Brightpan extraction API (null stub)")
DOCS: dict[str, dict] = {}

NULL_RECORD = {
    "vendor_name": None, "invoice_number": None, "invoice_date": None, "due_date": None,
    "currency": None, "po_number": None, "line_items": [], "subtotal": None, "discount": None,
    "tax": None, "shipping": None, "total": None, "confidence": {}, "flags": [], "route": None,
}


def now() -> datetime:
    return datetime.now(timezone.utc)


async def process(doc_id: str) -> None:
    doc = DOCS[doc_id]
    doc["status"] = "processing"
    await asyncio.sleep(0.05)
    finished = now()
    doc.update(status="done", record=dict(NULL_RECORD), finished_at=finished.isoformat(),
               processing_seconds=(finished - doc["_received"]).total_seconds())


@app.post("/documents", status_code=202)
async def upload(background: BackgroundTasks, file: UploadFile = File(...), source: str = Form("upload")):
    await file.read()
    doc_id = str(uuid.uuid4())
    received = now()
    DOCS[doc_id] = {"id": doc_id, "filename": file.filename, "source": source, "status": "queued",
                    "pages": None, "_received": received, "received_at": received.isoformat(),
                    "finished_at": None, "processing_seconds": None, "record": None,
                    "usage": {"model": "stub", "input_tokens": 0, "output_tokens": 0, "cost_usd": None},
                    "error": None}
    background.add_task(process, doc_id)
    return {"id": doc_id, "status": "queued"}


@app.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    if doc_id not in DOCS:
        raise HTTPException(404, "document not found")
    return {k: v for k, v in DOCS[doc_id].items() if not k.startswith("_")}


@app.post("/admin/reset")
async def reset():
    DOCS.clear()
    return {"ok": True}
