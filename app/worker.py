"""Background worker: claims queued documents from Postgres and processes them one at a time.

Runs inside the API process by default (a daemon thread started at app startup), or on its own:
  uv run python -m app.worker

The loop never dies on an error: database outages are retried with backoff, transient API errors put the
document back in the queue (up to db.MAX_ATTEMPTS), and every minute it requeues documents a stopped worker
left behind and resends register rows / Slack messages that didn't go out.
"""
import logging
import threading
import time

import anthropic
import psycopg

from . import config, db, notify
from .extract import ExtractionError, extract
from .validate import build_record, duplicate_key

log = logging.getLogger("worker")
POLL_SECONDS = 0.5
MAINTENANCE_SECONDS = 60
MAX_BACKOFF_SECONDS = 30

# Errors worth another attempt: rate limits, overload (529) and other 5xx, network/timeouts, and a database
# connection dropping. In the SDK, OverloadedError & co. are siblings of InternalServerError, so each is listed.
RETRYABLE = (anthropic.RateLimitError, anthropic.OverloadedError, anthropic.InternalServerError,
             anthropic.ServiceUnavailableError, anthropic.DeadlineExceededError, anthropic.APIConnectionError,
             psycopg.OperationalError)

# Read by /health.
state = {"thread": None, "last_poll": None}


def process(client: anthropic.Anthropic, doc: dict) -> None:
    result = extract(client, bytes(doc["file_bytes"]), doc["content_type"])
    x = result["extraction"]
    key = duplicate_key(x.vendor_name, x.invoice_number)
    record = build_record(x, is_duplicate=db.is_duplicate(key, doc["id"], doc["source"]),
                          threshold=config.CONFIDENCE_THRESHOLD, tolerance=config.TOLERANCE)
    db.save_result(doc["id"], record.model_dump(), key, result["pages"], result["input_mode"],
                   result["usage"], result["request_id"])
    log.info("%s %s route=%s flags=%s", doc["id"], doc["filename"], record.route, record.flags)
    # The document is done now. Sending is best effort: if it fails, the resend pass picks it up.
    safely("send outputs", lambda: db.set_outputs_status(doc["id"], notify.send(doc, record.model_dump())))


def resend_outputs() -> None:
    """Retries register rows and Slack messages that never went out (n8n down, a crash before sending)."""
    for row in db.pending_outputs():
        event = "review.approved" if row["review_status"] == "approved" else "document.processed"
        db.set_outputs_status(row["id"], notify.send(row, row["record"], event=event))


def safely(what: str, fn, *args) -> None:
    """Runs a database update whose failure must not stop the worker (the next maintenance pass catches up)."""
    try:
        fn(*args)
    except Exception:
        log.exception("could not %s", what)


def handle_failure(doc: dict, error: Exception) -> None:
    usage = getattr(error, "usage", None)
    message = f"{type(error).__name__}: {error}"
    if isinstance(error, RETRYABLE):
        log.warning("%s %s will be retried: %s", doc["id"], doc["filename"], message)
        safely("requeue the document", db.retry_later, doc["id"], message, doc["attempts"], usage)
    else:
        log.warning("%s %s failed: %s", doc["id"], doc["filename"], message)
        safely("mark the document failed", db.mark_failed, doc["id"], message, usage)


def run(stop: threading.Event | None = None) -> None:
    client = anthropic.Anthropic()
    backoff, last_maintenance = 1.0, 0.0
    while not (stop and stop.is_set()):
        try:
            if time.monotonic() - last_maintenance > MAINTENANCE_SECONDS:
                if n := db.requeue_stale():
                    log.info("requeued or failed %d stale documents", n)
                resend_outputs()
                last_maintenance = time.monotonic()
            doc = db.claim_next()
            state["last_poll"] = time.time()
            backoff = 1.0
        except Exception:
            log.exception("database unavailable; retrying in %.0fs", backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
            continue
        if doc is None:
            time.sleep(POLL_SECONDS)
            continue
        try:
            process(client, doc)
        except Exception as e:  # recorded on the document; the loop keeps going
            if not isinstance(e, (ExtractionError, anthropic.APIError, psycopg.Error)):
                log.exception("%s %s crashed", doc["id"], doc["filename"])
            handle_failure(doc, e)


def start_in_background() -> threading.Event:
    stop = threading.Event()
    thread = threading.Thread(target=run, args=(stop,), daemon=True, name="worker")
    thread.start()
    state["thread"] = thread
    return stop


def health() -> dict:
    thread, last = state["thread"], state["last_poll"]
    return {"running": bool(thread and thread.is_alive()),
            "seconds_since_poll": round(time.time() - last, 1) if last else None}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    db.init()
    run()
