"""Extraction API.  uv run uvicorn app.main:app --port 8040"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from . import config, db, worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
ACCEPTED = {"application/pdf", "image/jpeg", "image/png"}
MAX_BYTES = 20 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    stop = worker.start_in_background() if os.getenv("RUN_WORKER", "1") == "1" else None
    yield
    if stop:
        stop.set()
    db.pool.close()


app = FastAPI(title="Brightpan invoice extraction API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


def sniff(data: bytes, declared: str | None) -> str | None:
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG"):
        return "image/png"
    return declared if declared in ACCEPTED else None


@app.post("/documents", status_code=202)
async def upload(file: UploadFile = File(...), source: str = Form("upload")):
    data = await file.read()
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(413 if data else 400, "file is empty or larger than 20 MB")
    content_type = sniff(data, file.content_type)
    if content_type is None:
        raise HTTPException(415, "only PDF, JPEG and PNG are accepted")
    row = db.insert_document(file.filename or "upload", content_type, data, source)
    return {"id": str(row["id"]), "status": row["status"]}


@app.get("/documents/{document_id}")
def get_document(document_id: str):
    row = db.get_document(document_id)
    if row is None:
        raise HTTPException(404, "document not found")
    seconds = row["processing_seconds"]
    return {
        "id": str(row["id"]), "filename": row["filename"], "content_type": row["content_type"],
        "source": row["source"], "status": row["status"], "pages": row["pages"], "error": row["error"],
        "received_at": row["received_at"], "finished_at": row["finished_at"],
        "processing_seconds": float(seconds) if seconds is not None and row["status"] in ("done", "failed") else None,
        "record": row["record"], "input_mode": row["input_mode"],
        "review": {"status": row["review_status"], "note": row["reviewer_note"]} if row["review_status"] else None,
        "usage": {"model": row["model"], "input_tokens": row["input_tokens"], "output_tokens": row["output_tokens"],
                  "cost_usd": float(row["cost_usd"]) if row["cost_usd"] is not None else None},
    }


@app.get("/documents/{document_id}/file")
def get_file(document_id: str):
    row = db.get_file(document_id)
    if row is None:
        raise HTTPException(404, "document not found")
    return Response(bytes(row["file_bytes"]), media_type=row["content_type"],
                    headers={"Content-Disposition": f'inline; filename="{row["filename"]}"'})


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/admin/reset")
def reset():
    if not config.ALLOW_RESET:
        raise HTTPException(403, "reset is disabled (set ALLOW_RESET=1 for local eval runs)")
    db.reset()
    return {"ok": True}
