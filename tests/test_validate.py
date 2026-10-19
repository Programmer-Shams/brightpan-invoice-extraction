import json
from pathlib import Path

from app.models import Extraction
from app.validate import build_record, check_totals, duplicate_key, missing_required

TRUTH = Path(__file__).resolve().parent.parent / "truth"
HIGH = {f: 0.95 for f in Extraction.model_fields["confidence"].annotation.model_fields}


def from_truth(doc_id: str, **overrides) -> Extraction:
    t = json.loads((TRUTH / f"{doc_id}.json").read_text())
    fields = {k: t[k] for k in Extraction.model_fields if k != "confidence"}
    return Extraction(**{**fields, "confidence": HIGH, **overrides})


def record(x: Extraction, dup: bool = False):
    return build_record(x, is_duplicate=dup, threshold=0.80, tolerance=0.02)


def test_every_clean_truth_document_routes_auto():
    for p in sorted(TRUTH.glob("*.json")):
        t = json.loads(p.read_text())
        if t["expected_route"] == "auto":
            r = record(from_truth(t["document_id"]))
            assert (r.route, r.flags) == ("auto", []), t["document_id"]


def test_inv10_printed_total_is_kept_and_flagged():
    r = record(from_truth("INV10"))
    assert r.total == 490.0                        # never corrected
    assert r.flags == ["totals_mismatch"] and r.route == "review"
    assert r.checks["totals"]["computed_total"] == 440.0


def test_discount_and_tax_are_in_the_total_math():
    assert check_totals(from_truth("INV07"), 0.02)[0]          # 1140 - 90 = 1050
    assert check_totals(from_truth("INV06"), 0.02)[0]          # CAD with 5% GST and shipping


def test_tolerance_is_two_cents():
    assert check_totals(from_truth("INV01", total=3202.52), 0.02)[0]
    assert not check_totals(from_truth("INV01", total=3202.53), 0.02)[0]


def test_line_sum_must_match_subtotal():
    x = from_truth("INV02", subtotal=550.0, total=550.0)       # subtotal and total agree, lines don't
    ok, checks = check_totals(x, 0.02)
    assert not ok and checks["line_sum_minus_subtotal"] == -3.0


def test_missing_and_invalid_required_fields():
    assert missing_required(from_truth("INV01", invoice_number=None)) == ["invoice_number"]
    assert missing_required(from_truth("INV01", invoice_date="09/02/2026")) == ["invoice_date (not YYYY-MM-DD)"]
    assert missing_required(from_truth("INV01", currency="US$")) == ["currency ('US$' not ISO 4217)"]
    assert missing_required(from_truth("RCPT01")) == []        # null due_date is fine on a receipt
    r = record(from_truth("INV01", currency=None))
    assert "missing_required_field" in r.flags and r.route == "review"


def test_low_confidence_on_a_required_field_routes_to_review():
    r = record(from_truth("INV15", confidence={**HIGH, "total": 0.6}))
    assert r.flags == ["low_confidence"] and r.checks["low_confidence_fields"] == ["total"]
    r = record(from_truth("INV15", confidence={**HIGH, "po_number": 0.3}))   # not a required field
    assert r.route == "auto"


def test_duplicate_flag_routes_to_review():
    r = record(from_truth("INV16"), dup=True)
    assert r.flags == ["duplicate_invoice"] and r.route == "review"


def test_duplicate_key_ignores_case_spacing_and_punctuation():
    assert duplicate_key("Ferro Metalworks Inc.", "FM-10421") == duplicate_key("FERRO METALWORKS INC", "fm 10421")
    assert duplicate_key("Ferro Metalworks Inc.", "FM-10421") != duplicate_key("Ferro Metalworks Inc.", "FM-10498")
    assert duplicate_key("Ferro Metalworks Inc.", "FM-10421") != duplicate_key("Pacific Packaging Co.", "FM-10421")
    assert duplicate_key(None, "FM-10421") is None and duplicate_key("Ferro", "") is None


def test_exactly_two_cents_is_within_tolerance_despite_float_error():
    # 0.10 - 0.08 is 0.020000000000000004 in floats; the spec allows +-$0.02
    x = from_truth("INV01", line_items=[{"description": "a", "quantity": 1, "unit_price": 0.08, "amount": 0.08}],
                   subtotal=0.10, discount=0.0, tax=0.0, shipping=0.0, total=0.10)
    assert check_totals(x, 0.02)[0]
    assert not check_totals(from_truth("INV01", subtotal=3057.47, total=3202.47), 0.02)[0]  # 3 cents off
