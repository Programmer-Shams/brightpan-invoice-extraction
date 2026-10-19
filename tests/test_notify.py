import json
from datetime import datetime, timezone
from pathlib import Path

from app import notify
from app.validate import build_record
from tests.test_validate import from_truth

ROOT = Path(__file__).resolve().parent.parent
DOC = {"id": "00000000-0000-0000-0000-000000000010", "filename": "INV10.pdf", "source": "upload",
       "received_at": datetime(2026, 10, 19, 18, 0, tzinfo=timezone.utc)}


def rec(doc_id, dup=False):
    return build_record(from_truth(doc_id), is_duplicate=dup, threshold=0.8, tolerance=0.02).model_dump()


def test_slack_message_explains_totals_mismatch():
    text = notify.slack_message(DOC, rec("INV10"))["text"]
    assert "Pacific Packaging Co. PP-88377" in text
    assert "printed USD 490.00, lines add up to USD 440.00" in text
    assert "/review/00000000-0000-0000-0000-000000000010" in text


def test_slack_message_explains_duplicate():
    assert "duplicate of an invoice already received" in notify.slack_message(DOC, rec("INV16", dup=True))["text"]


def test_sheet_row_has_register_columns_and_blank_nulls():
    row = notify.sheet_row({**DOC, "filename": "RCPT01.png"}, rec("RCPT01"))
    assert row["Vendor"] == "OfficeHub Supplies" and row["Total"] == 74.49 and row["Line items"] == 2
    assert row["Due date"] == "" and row["PO #"] == ""          # receipts: never invented
    assert row["Received"] == "2026-10-19T18:00:00+00:00"


def test_eval_uploads_are_not_sent(monkeypatch):
    monkeypatch.setattr(notify.config, "NOTIFY_EVAL", False)
    assert notify.send({**DOC, "source": "eval"}, rec("INV01")) == "skipped:eval upload"


def test_document_text_cannot_inject_formulas_or_slack_markup():
    evil = {**rec("INV10"), "vendor_name": "=HYPERLINK(\"http://x\",\"pay\")", "invoice_number": "<!channel|x>"}
    row = notify.sheet_row({**DOC, "filename": "+cmd.pdf"}, evil)
    assert row["Vendor"] == "=HYPERLINK(\"http://x\",\"pay\")"   # stored literally: the Sheets step writes RAW
    assert row["Total"] == 490.0                                  # numbers stay numbers
    wf = json.loads((ROOT / "n8n" / "ap-outputs.workflow.json").read_text())
    sheets = next(n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.googleSheets")
    assert sheets["parameters"]["options"]["cellFormat"] == "RAW"
    text = notify.slack_message({**DOC, "filename": "<http://evil|invoice>.pdf"}, evil)["text"]
    assert "<!channel" not in text and "<http://evil" not in text and "&lt;!channel|x&gt;" in text
