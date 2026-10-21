import hashlib
from pathlib import Path

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from . import config

pool = ConnectionPool(config.DATABASE_URL, min_size=1, max_size=5, open=False,
                      check=ConnectionPool.check_connection,  # drop connections the pooler closed
                      kwargs={"row_factory": dict_row, "options": f"-c search_path={config.DB_SCHEMA}",
                              "prepare_threshold": None})  # no server-side prepares: safe behind Supabase's pooler


def ping() -> bool:
    try:
        with pool.connection(timeout=5) as conn:
            conn.execute("select 1")
        return True
    except Exception:
        return False


def init() -> None:
    pool.open(wait=True)
    with pool.connection() as conn:
        conn.execute((Path(__file__).parent / "schema.sql").read_text())


def insert_document(filename: str, content_type: str, data: bytes, source: str) -> dict:
    with pool.connection() as conn:
        return conn.execute(
            "insert into documents (filename, content_type, source, file_bytes, sha256) values (%s, %s, %s, %s, %s) "
            "returning id, status", (filename, content_type, source, data, hashlib.sha256(data).hexdigest())).fetchone()


MAX_ATTEMPTS = 3


def claim_next() -> dict | None:
    """Oldest queued document that is due, locked so concurrent workers never take the same one."""
    with pool.connection() as conn:
        return conn.execute(
            "update documents set status = 'processing', started_at = now(), attempts = attempts + 1 "
            "where id = (select id from documents where status = 'queued' and (retry_at is null or retry_at <= now()) "
            "            order by received_at for update skip locked limit 1) "
            "returning id, filename, content_type, source, received_at, attempts, file_bytes").fetchone()


def requeue_stale(minutes: int = 10) -> int:
    """Documents left 'processing' by a worker that stopped go back to the queue, unless they have used up their
    attempts (a document that keeps crashing the worker must not loop forever)."""
    with pool.connection() as conn:
        failed = conn.execute(
            "update documents set status = 'failed', finished_at = now(), "
            "error = 'Stopped while being read ' || attempts || ' times; not retried again' "
            "where status = 'processing' and started_at < now() - make_interval(mins => %s) and attempts >= %s",
            (minutes, MAX_ATTEMPTS)).rowcount
        return failed + conn.execute(
            "update documents set status = 'queued' where status = 'processing' "
            "and started_at < now() - make_interval(mins => %s)", (minutes,)).rowcount


def retry_later(document_id, error: str, attempts: int, usage: dict | None) -> bool:
    """Puts a document back in the queue after a transient failure. Returns False once attempts are used up."""
    if attempts >= MAX_ATTEMPTS:
        mark_failed(document_id, f"{error} (after {attempts} attempts)", usage)
        return False
    with pool.connection() as conn:
        conn.execute("update documents set status = 'queued', error = %s, "
                     "retry_at = now() + make_interval(secs => %s), "
                     "failure_usage = coalesce(%s, failure_usage) where id = %s and status = 'processing'",
                     (error[:2000], 30 * 2 ** (attempts - 1), Jsonb(usage) if usage else None, document_id))
    return True


# Same vendor + invoice number already stored, by another document in the same scope. Eval uploads are their own
# scope, so the test set never marks a real invoice as a duplicate (or the other way round). Tested in
# tests/test_duplicates_db.py against a throwaway schema.
DUPLICATE_SQL = ("select 1 from extractions e join documents d on d.id = e.document_id "
                 "where e.duplicate_key = %s and e.document_id <> %s and (d.source = 'eval') = %s limit 1")


def save_result(document_id, build, key: str | None, source: str, pages: int, input_mode: str, usage: dict,
                request_id: str | None) -> dict:
    """Checks for a duplicate and stores the record in one transaction, under a lock on the duplicate key, so two
    workers reading copies of the same invoice at the same moment can't both miss each other.
    `build(is_duplicate)` returns the record to store."""
    with pool.connection() as conn, conn.transaction():
        is_dup = False
        if key is not None:
            conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (key,))
            is_dup = conn.execute(DUPLICATE_SQL, (key, document_id, source == "eval")).fetchone() is not None
        record = build(is_dup)
        conn.execute(
            "insert into extractions (document_id, record, vendor_name, invoice_number, duplicate_key, route, flags, "
            "input_mode, model, input_tokens, output_tokens, cost_usd, request_id) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (document_id, Jsonb(record), record["vendor_name"], record["invoice_number"], key, record["route"],
             record["flags"], input_mode, usage["model"], usage["input_tokens"], usage["output_tokens"],
             usage["cost_usd"], request_id))
        if record["route"] == "review":
            conn.execute("insert into review_queue (document_id, reasons) values (%s, %s)",
                         (document_id, record["flags"]))
        conn.execute("update documents set status = 'done', pages = %s, finished_at = now(), error = null "
                     "where id = %s", (pages, document_id))
    return record


def requeue_failed(document_id) -> bool:
    """Puts a failed document back in the queue for a fresh read (a person asked for it), with a full set of attempts."""
    with pool.connection() as conn:
        return conn.execute("update documents set status = 'queued', attempts = 0, error = null, retry_at = null, "
                            "started_at = null, finished_at = null where id = %s and status = 'failed'",
                            (document_id,)).rowcount == 1


def mark_failed(document_id, error: str, usage: dict | None = None) -> None:
    with pool.connection() as conn:
        conn.execute("update documents set status = 'failed', error = %s, finished_at = now(), "
                     "failure_usage = coalesce(%s, failure_usage) where id = %s and status = 'processing'",
                     (error[:2000], Jsonb(usage) if usage else None, document_id))


def set_outputs_status(document_id, status: str) -> None:
    with pool.connection() as conn:
        conn.execute("update extractions set outputs_status = %s, outputs_attempts = outputs_attempts + 1 "
                     "where document_id = %s", (status, document_id))


MAX_OUTPUT_ATTEMPTS = 5


def pending_outputs(limit: int = 10) -> list[dict]:
    """Register rows / Slack messages that were never sent or failed, for the worker to retry."""
    with pool.connection() as conn:
        return conn.execute(
            "select d.id, d.filename, d.source, d.received_at, e.record, r.status as review_status "
            "from extractions e join documents d on d.id = e.document_id "
            "left join review_queue r on r.document_id = d.id "
            "where d.source <> 'eval' and e.outputs_attempts < %s and r.status is distinct from 'rejected' and "
            "      (e.outputs_status like 'failed:%%' or (e.outputs_status is null and e.created_at < now() - interval '1 minute')) "
            "order by e.created_at limit %s", (MAX_OUTPUT_ATTEMPTS, limit)).fetchall()


def get_document(document_id) -> dict | None:
    with pool.connection() as conn:
        return conn.execute(
            "select d.id, d.filename, d.content_type, d.source, d.status, d.pages, d.error, d.received_at, "
            "d.finished_at, extract(epoch from d.finished_at - d.received_at) as processing_seconds, "
            "e.record, e.model, e.input_tokens, e.output_tokens, e.cost_usd, e.input_mode, e.outputs_status, "
            "e.outputs_attempts, "
            "d.failure_usage, "
            "r.status as review_status, r.reviewer_note "
            "from documents d left join extractions e on e.document_id = d.id "
            "left join review_queue r on r.document_id = d.id where d.id = %s", (document_id,)).fetchone()


def get_file(document_id) -> dict | None:
    with pool.connection() as conn:
        return conn.execute("select filename, content_type, file_bytes from documents where id = %s",
                            (document_id,)).fetchone()


def reset_eval() -> int:
    """Removes eval uploads only; real uploads and emails are kept."""
    with pool.connection() as conn:
        return conn.execute("delete from documents where source = 'eval'").rowcount


SUMMARY_COLUMNS = (
    "d.id, d.filename, d.content_type, d.source, d.status, d.pages, d.error, d.received_at, d.finished_at, "
    "extract(epoch from d.finished_at - d.received_at) as processing_seconds, "
    "e.record->>'vendor_name' as vendor_name, e.record->>'invoice_number' as invoice_number, "
    "e.record->>'currency' as currency, (e.record->>'total')::numeric as total, e.route, e.flags, e.cost_usd, "
    "e.outputs_status, "
    "r.status as review_status, r.reasons as review_reasons")
SUMMARY_JOINS = ("from documents d left join extractions e on e.document_id = d.id "
                 "left join review_queue r on r.document_id = d.id")


def list_documents(limit: int, include_eval: bool) -> list[dict]:
    with pool.connection() as conn:
        return conn.execute(f"select {SUMMARY_COLUMNS} {SUMMARY_JOINS} where %s or d.source <> 'eval' "
                            "order by d.received_at desc limit %s", (include_eval, limit)).fetchall()


def list_review(status: str, include_eval: bool) -> list[dict]:
    with pool.connection() as conn:
        return conn.execute(f"select {SUMMARY_COLUMNS} {SUMMARY_JOINS} where r.status = %s "
                            "and (%s or d.source <> 'eval') order by r.created_at", (status, include_eval)).fetchall()


def resolve_review(document_id, status: str, note: str | None) -> dict | None:
    """Closes an open review item. Returns the document (with record) or None if nothing was open.
    Approving starts a new delivery (the register row), so its send attempts start from zero."""
    with pool.connection() as conn, conn.transaction():
        row = conn.execute("update review_queue set status = %s, reviewer_note = %s, resolved_at = now() "
                           "where document_id = %s and status = 'open' returning document_id",
                           (status, note, document_id)).fetchone()
        if row:
            conn.execute("update extractions set outputs_attempts = 0, outputs_status = null where document_id = %s",
                         (document_id,))
    return get_document(document_id) if row else None
