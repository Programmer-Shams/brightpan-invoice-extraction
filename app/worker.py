"""Background worker: claims queued documents from Postgres and processes them one at a time.

Runs inside the API process by default (a daemon thread started at app startup), or on its own:
  uv run python -m app.worker
"""
import logging
import threading
import time

import anthropic

from . import config, db, notify
from .extract import ExtractionError, extract
from .validate import build_record, duplicate_key

log = logging.getLogger("worker")
POLL_SECONDS = 0.5


def process(client: anthropic.Anthropic, doc: dict) -> None:
    result = extract(client, bytes(doc["file_bytes"]), doc["content_type"])
    x = result["extraction"]
    key = duplicate_key(x.vendor_name, x.invoice_number)
    record = build_record(x, is_duplicate=db.is_duplicate(key, doc["id"]),
                          threshold=config.CONFIDENCE_THRESHOLD, tolerance=config.TOLERANCE)
    db.save_result(doc["id"], record.model_dump(), key, result["pages"], result["input_mode"],
                   result["usage"], result["request_id"])
    db.set_outputs_status(doc["id"], notify.send(doc, record.model_dump()))
    log.info("%s %s route=%s flags=%s", doc["id"], doc["filename"], record.route, record.flags)


def run(stop: threading.Event | None = None) -> None:
    client = anthropic.Anthropic()
    db.requeue_stale()
    while not (stop and stop.is_set()):
        doc = db.claim_next()
        if doc is None:
            time.sleep(POLL_SECONDS)
            continue
        try:
            process(client, doc)
        except (ExtractionError, anthropic.APIError) as e:
            log.warning("%s %s failed: %s", doc["id"], doc["filename"], e)
            db.mark_failed(doc["id"], f"{type(e).__name__}: {e}")
        except Exception as e:  # keep the worker alive; the document records the failure
            log.exception("%s %s crashed", doc["id"], doc["filename"])
            db.mark_failed(doc["id"], f"{type(e).__name__}: {e}")


def start_in_background() -> threading.Event:
    stop = threading.Event()
    threading.Thread(target=run, args=(stop,), daemon=True, name="worker").start()
    return stop


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    db.init()
    run()
