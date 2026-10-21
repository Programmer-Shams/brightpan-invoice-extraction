import anthropic
import psycopg

from app import worker
from tests.test_validate import from_truth

DOC = {"id": "d1", "filename": "INV01.pdf", "content_type": "application/pdf", "source": "upload", "attempts": 1,
       "file_bytes": b"%PDF-", "received_at": None}


def test_transient_api_errors_are_retried():
    for cls in (anthropic.OverloadedError, anthropic.RateLimitError, anthropic.InternalServerError,
                anthropic.ServiceUnavailableError, anthropic.APITimeoutError, psycopg.OperationalError):
        assert issubclass(cls, worker.RETRYABLE), cls.__name__
    assert not issubclass(anthropic.BadRequestError, worker.RETRYABLE)   # e.g. "credit balance too low"


def test_failure_after_the_result_is_saved_does_not_reopen_the_document(monkeypatch):
    calls = []
    monkeypatch.setattr(worker, "extract", lambda *a: {"extraction": from_truth("INV01"), "pages": 1,
                                                       "input_mode": "pdf_text", "usage": {}, "request_id": "r"})
    monkeypatch.setattr(worker.db, "save_result", lambda _id, build, *a: (calls.append("saved"), build(False))[1])
    monkeypatch.setattr(worker.notify, "send", lambda *a, **k: (_ for _ in ()).throw(psycopg.OperationalError("blip")))
    monkeypatch.setattr(worker.db, "retry_later", lambda *a: calls.append("requeued"))
    monkeypatch.setattr(worker.db, "mark_failed", lambda *a: calls.append("failed"))
    worker.process(None, DOC)                      # must not raise: the resend pass delivers the outputs later
    worker.outputs.submit(lambda: None).result(timeout=5)   # let the outputs thread finish its (failing) send
    assert calls == ["saved"]


def test_outputs_are_sent_off_the_worker_thread(monkeypatch):
    import threading, time
    sent = threading.Event()
    monkeypatch.setattr(worker, "extract", lambda *a: {"extraction": from_truth("INV01"), "pages": 1,
                                                       "input_mode": "pdf_text", "usage": {}, "request_id": "r"})
    monkeypatch.setattr(worker.db, "save_result", lambda _id, build, *a: build(False))
    monkeypatch.setattr(worker.notify, "send", lambda *a, **k: (time.sleep(1), "sent")[1])
    monkeypatch.setattr(worker.db, "set_outputs_status", lambda *a: sent.set())
    t = time.monotonic()
    worker.process(None, DOC)
    assert time.monotonic() - t < 0.5               # the slow register write doesn't hold up the next document
    assert sent.wait(5)                             # and it is still delivered
