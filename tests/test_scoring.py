import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
from scoring import compute_metrics, score_document  # noqa: E402

TRUTH = {p.stem: json.loads(p.read_text()) for p in sorted((ROOT / "truth").glob("*.json"))}
N_LINES = sum(len(t["line_items"]) for t in TRUTH.values())


def response(record):
    return {"status": "done", "record": record, "processing_seconds": 2.0, "pages": 1,
            "usage": {"model": "test", "input_tokens": 10, "output_tokens": 5, "cost_usd": 0.01}}


def perfect(t):
    rec = {k: t[k] for k in ["vendor_name", "invoice_number", "invoice_date", "due_date", "currency",
                             "po_number", "line_items", "subtotal", "discount", "tax", "shipping", "total"]}
    return {**rec, "flags": t["expected_flags"], "route": t["expected_route"], "confidence": {}}


def test_perfect_records_score_100():
    rows = [r for t in TRUTH.values() for r in score_document(t, response(perfect(t)))]
    m = compute_metrics(rows)
    assert m["field_accuracy"] == "200/200 (100.0%)"
    assert m["line_item_accuracy"].startswith(f"{N_LINES}/{N_LINES}")
    assert m["planted_caught"].startswith("2/2")
    assert m["false_reviews"] == "0/18"
    assert m["invented_values"] == 0


def test_null_record_scores_only_truth_nulls():
    rows = [r for t in TRUTH.values() for r in score_document(t, response({}))]
    m = compute_metrics(rows)
    truth_nulls = sum(t[f] is None for t in TRUTH.values() for f in ["due_date", "po_number"])
    assert m["field_accuracy"].startswith(f"{truth_nulls}/200")
    assert m["line_item_accuracy"].startswith(f"0/{N_LINES}")
    assert m["planted_caught"].startswith("0/2")


def test_formatting_and_invention_are_strict():
    t = TRUTH["INV06"]
    rec = {**perfect(t), "vendor_name": "Maple Leaf Ceramics Ltd", "currency": "USD", "total": 2481.14}
    rows = {r["field"]: r for r in score_document(t, response(rec)) if r["kind"] == "header"}
    assert rows["vendor_name"]["match"] == 0          # "Ltd." vs "Ltd" is left to the manual review
    assert rows["currency"]["invented"] == 1          # USD on a CAD invoice
    assert rows["total"]["match"] == 0                # off by a cent
    rcpt = {**perfect(TRUTH["RCPT01"]), "due_date": "2026-11-08"}
    rows = {r["field"]: r for r in score_document(TRUTH["RCPT01"], response(rcpt)) if r["kind"] == "header"}
    assert rows["due_date"]["invented"] == 1


def test_line_items_order_independent_and_extras_counted():
    t = TRUTH["INV02"]
    rec = {**perfect(t), "line_items": list(reversed(t["line_items"])) + [{"description": "x", "quantity": 1,
                                                                          "unit_price": 1, "amount": 1}]}
    m = compute_metrics(score_document(t, response(rec)))
    assert m["line_item_accuracy"].startswith("3/3")
    assert m["extra_line_items"] == 1
