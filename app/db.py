import hashlib
from pathlib import Path

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from . import config

pool = ConnectionPool(config.DATABASE_URL, min_size=1, max_size=5, open=False,
                      kwargs={"row_factory": dict_row, "options": f"-c search_path={config.DB_SCHEMA}",
                              "prepare_threshold": None})  # no server-side prepares: safe behind Supabase's pooler


def init() -> None:
    pool.open(wait=True)
    with pool.connection() as conn:
        conn.execute((Path(__file__).parent / "schema.sql").read_text())


def insert_document(filename: str, content_type: str, data: bytes, source: str) -> dict:
    with pool.connection() as conn:
        return conn.execute(
            "insert into documents (filename, content_type, source, file_bytes, sha256) values (%s, %s, %s, %s, %s) "
            "returning id, status", (filename, content_type, source, data, hashlib.sha256(data).hexdigest())).fetchone()


def claim_next() -> dict | None:
    """Oldest queued document, locked so concurrent workers never take the same one."""
    with pool.connection() as conn:
        return conn.execute(
            "update documents set status = 'processing', started_at = now(), attempts = attempts + 1 "
            "where id = (select id from documents where status = 'queued' order by received_at "
            "            for update skip locked limit 1) "
            "returning id, filename, content_type, source, received_at, file_bytes").fetchone()


def requeue_stale(minutes: int = 10) -> int:
    """Documents left 'processing' by a crashed worker go back to the queue."""
    with pool.connection() as conn:
        return conn.execute("update documents set status = 'queued' where status = 'processing' "
                            "and started_at < now() - make_interval(mins => %s)", (minutes,)).rowcount


def is_duplicate(key: str | None, document_id, source: str) -> bool:
    """Same vendor + invoice number already stored. Eval uploads are their own scope, so the test set
    never marks a real invoice as a duplicate (or the other way round)."""
    if key is None:
        return False
    with pool.connection() as conn:
        return conn.execute(
            "select 1 from extractions e join documents d on d.id = e.document_id "
            "where e.duplicate_key = %s and e.document_id <> %s and (d.source = 'eval') = %s limit 1",
            (key, document_id, source == "eval")).fetchone() is not None


def save_result(document_id, record: dict, key: str | None, pages: int, input_mode: str, usage: dict,
                request_id: str | None) -> None:
    with pool.connection() as conn, conn.transaction():
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


def set_outputs_status(document_id, status: str) -> None:
    with pool.connection() as conn:
        conn.execute("update extractions set outputs_status = %s where document_id = %s", (status, document_id))


def mark_failed(document_id, error: str) -> None:
    with pool.connection() as conn:
        conn.execute("update documents set status = 'failed', error = %s, finished_at = now() where id = %s",
                     (error[:2000], document_id))


def get_document(document_id) -> dict | None:
    with pool.connection() as conn:
        return conn.execute(
            "select d.id, d.filename, d.content_type, d.source, d.status, d.pages, d.error, d.received_at, "
            "d.finished_at, extract(epoch from d.finished_at - d.received_at) as processing_seconds, "
            "e.record, e.model, e.input_tokens, e.output_tokens, e.cost_usd, e.input_mode, e.outputs_status, "
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
