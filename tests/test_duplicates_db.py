"""The duplicate check's SQL against a real Postgres, in a throwaway schema that is dropped afterwards.
Runs only when TEST_DATABASE_URL is set, so a plain `pytest` never touches a real database."""
import os
import uuid

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app import config
from app.db import DUPLICATE_SQL
from app.validate import duplicate_key

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="set TEST_DATABASE_URL to run the database tests")
KEY = duplicate_key("Ferro Metalworks Inc.", "FM-10421")


@pytest.fixture
def conn():
    schema = f"dup_test_{uuid.uuid4().hex[:8]}"
    sql = (config.ROOT / "app" / "schema.sql").read_text().replace("invoice_extraction", schema)
    with psycopg.connect(TEST_DATABASE_URL, prepare_threshold=None, autocommit=True) as c:
        c.execute(sql)
        try:
            yield c
        finally:
            c.execute(f"drop schema {schema} cascade")


def stored(conn, source: str, key: str | None = KEY):
    doc = conn.execute("insert into documents (filename, content_type, source, file_bytes, sha256, status) "
                       "values ('x.pdf', 'application/pdf', %s, '\\x00', 'h', 'done') returning id", (source,)).fetchone()[0]
    conn.execute("insert into extractions (document_id, record, duplicate_key, route) values (%s, %s, %s, 'auto')",
                 (doc, Jsonb({}), key))
    return doc


def dup(conn, doc, source: str) -> bool:
    return conn.execute(DUPLICATE_SQL, (KEY, doc, source == "eval")).fetchone() is not None


def test_second_invoice_with_same_key_is_a_duplicate_and_the_first_is_not_itself(conn):
    first = stored(conn, "upload")
    assert not dup(conn, first, "upload")              # a document never duplicates itself
    second = stored(conn, "email")                      # email and upload share one scope
    assert dup(conn, second, "email")


def test_eval_uploads_are_a_separate_scope(conn):
    real = stored(conn, "upload")
    test_copy = stored(conn, "eval")
    assert not dup(conn, test_copy, "eval")             # the eval INV01 isn't a duplicate of a real one
    assert not dup(conn, real, "upload")                # and the eval copy doesn't make the real one a duplicate
    assert dup(conn, stored(conn, "eval"), "eval")      # the eval INV16 still finds the eval INV01


def test_different_key_is_not_a_duplicate(conn):
    stored(conn, "upload", key=duplicate_key("Ferro Metalworks Inc.", "FM-10498"))
    other = stored(conn, "upload", key=None)
    assert not dup(conn, other, "upload")


def test_two_copies_saved_at_the_same_moment_still_catch_each_other(conn):
    """The worker's save path: lock on the key, check, insert, all in one transaction (as app.db.save_result)."""
    import threading
    schema = conn.execute("select current_schema()").fetchone()[0]
    results, barrier = [], threading.Barrier(2)

    def save(source):
        with psycopg.connect(TEST_DATABASE_URL, prepare_threshold=None, options=f"-c search_path={schema}") as c:
            doc = c.execute("insert into documents (filename, content_type, source, file_bytes, sha256, status) "
                            "values ('x.pdf', 'application/pdf', %s, '\\x00', 'h', 'processing') returning id",
                            (source,)).fetchone()[0]
            c.commit()
            barrier.wait()
            with c.transaction():
                c.execute("select pg_advisory_xact_lock(hashtext(%s))", (KEY,))
                dup = c.execute(DUPLICATE_SQL, (KEY, doc, False)).fetchone() is not None
                c.execute("insert into extractions (document_id, record, duplicate_key, route) values (%s, %s, %s, 'auto')",
                          (doc, Jsonb({}), KEY))
            results.append(dup)

    threads = [threading.Thread(target=save, args=(s,)) for s in ("upload", "email")]
    for t in threads: t.start()
    for t in threads: t.join()
    assert sorted(results) == [False, True]      # exactly one of the two is flagged as the duplicate
