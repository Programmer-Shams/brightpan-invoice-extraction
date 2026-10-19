"""Compares extracted records with truth/ and computes the BUILD_SPEC metrics.

Scoring is deliberately strict; the manual review (step 5) decides formatting-only mismatches
such as "Inc." vs "Inc". Every metric is computed from result rows, so it can be recomputed
from eval/results.csv alone.
"""
import statistics
from typing import Any

HEADER_FIELDS = ["vendor_name", "invoice_number", "invoice_date", "due_date", "currency",
                 "po_number", "subtotal", "tax", "shipping", "total"]
STRING_FIELDS = {"vendor_name", "invoice_number", "invoice_date", "due_date", "currency", "po_number"}
LINE_FIELDS = ["description", "quantity", "unit_price", "amount"]
FORMAT_GROUPS = {"digital": "digital", "multipage": "digital", "scan": "scan", "photo": "photo",
                 "receipt": "receipt"}
TOLERANCE = 0.005  # numbers must agree to the cent
CSV_COLUMNS = ["document_id", "format", "kind", "field", "expected", "actual", "match", "invented"]


def norm_text(v: Any) -> str:
    return " ".join(str(v).split()).casefold()


def is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def values_match(field: str, expected: Any, actual: Any) -> bool:
    if expected is None or actual is None:
        return expected is None and actual is None
    if field in STRING_FIELDS or field == "description":
        return isinstance(actual, str) and norm_text(expected) == norm_text(actual)
    return is_number(actual) and abs(float(expected) - float(actual)) < TOLERANCE


def line_matches(expected: dict, actual: dict) -> bool:
    return all(values_match(f, expected.get(f), actual.get(f)) for f in LINE_FIELDS)


def fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return ";".join(str(x) for x in v)
    return str(v)


def fmt_line(item: dict | None) -> str:
    return "" if item is None else " | ".join(fmt(item.get(f)) for f in LINE_FIELDS)


def pair_lines(truth_lines: list[dict], actual_lines: list[dict]):
    """Order-independent: each truth line takes an unused extracted line matching on all four fields.
    Unmatched truth lines are paired, for display, with the leftover extracted lines in order."""
    used, pairs = set(), [None] * len(truth_lines)
    for i, t in enumerate(truth_lines):
        for j, a in enumerate(actual_lines):
            if j not in used and isinstance(a, dict) and line_matches(t, a):
                used.add(j)
                pairs[i] = (a, True)
                break
    leftovers = [a for j, a in enumerate(actual_lines) if j not in used]
    for i in range(len(truth_lines)):
        if pairs[i] is None:
            pairs[i] = (leftovers.pop(0) if leftovers else None, False)
    return pairs, leftovers


def score_document(truth: dict, response: dict | None) -> list[dict]:
    """Rows for one document. `response` is the API's GET /documents/{id} body (None if never finished)."""
    doc_id, fmt_ = truth["document_id"], truth["format"]
    response = response or {}
    record = response.get("record") or {}
    rows = []

    def row(kind, field, expected, actual, match, invented=""):
        rows.append({"document_id": doc_id, "format": fmt_, "kind": kind, "field": field,
                     "expected": expected, "actual": actual, "match": match, "invented": invented})

    for f in HEADER_FIELDS:
        exp, act = truth.get(f), record.get(f)
        invented = (exp is None and act is not None) or \
                   (f == "currency" and exp == "CAD" and isinstance(act, str) and act.strip().upper() == "USD")
        row("header", f, fmt(exp), fmt(act), int(values_match(f, exp, act)), int(invented))

    actual_lines = record.get("line_items") or []
    pairs, extras = pair_lines(truth["line_items"], actual_lines)
    for i, (t, (a, ok)) in enumerate(zip(truth["line_items"], pairs), start=1):
        row("line_item", f"line {i}", fmt_line(t), fmt_line(a), int(ok))
    for a in extras:
        row("line_item_extra", "extra", "", fmt_line(a if isinstance(a, dict) else {}), 0)

    row("route", "route", truth["expected_route"], fmt(record.get("route")),
        int(record.get("route") == truth["expected_route"]))
    exp_flags, act_flags = sorted(truth["expected_flags"]), sorted(record.get("flags") or [])
    row("flags", "flags", fmt(exp_flags), fmt(act_flags), int(exp_flags == act_flags))

    usage = response.get("usage") or {}
    for field, value in [("status", response.get("status", "not_finished")),
                         ("pages", response.get("pages")),
                         ("seconds", response.get("processing_seconds")),
                         ("seconds_source", response.get("seconds_source")),
                         ("model", usage.get("model")),
                         ("input_tokens", usage.get("input_tokens")),
                         ("output_tokens", usage.get("output_tokens")),
                         ("cost_usd", usage.get("cost_usd")),
                         ("error", response.get("error"))]:
        row("meta", field, "", fmt(value), "")
    return rows


def _num(v: str) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.1f}%)" if d else "0/0"


def compute_metrics(rows: list[dict]) -> dict:
    """All metrics from result rows (dicts from score_document or read back from results.csv)."""
    is_ok = lambda r: str(r["match"]) == "1"
    header = [r for r in rows if r["kind"] == "header"]
    lines = [r for r in rows if r["kind"] == "line_item"]
    m: dict[str, Any] = {}

    m["field_accuracy"] = _pct(sum(map(is_ok, header)), len(header))
    by_format = {}
    for group in ["digital", "scan", "photo", "receipt"]:
        g = [r for r in header if FORMAT_GROUPS.get(r["format"], r["format"]) == group]
        by_format[group] = _pct(sum(map(is_ok, g)), len(g))
    m["field_accuracy_by_format"] = by_format
    by_field = {}
    for f in HEADER_FIELDS:
        g = [r for r in header if r["field"] == f]
        by_field[f] = _pct(sum(map(is_ok, g)), len(g))
    m["field_accuracy_by_field"] = by_field

    m["line_item_accuracy"] = _pct(sum(map(is_ok, lines)), len(lines))
    m["extra_line_items"] = sum(1 for r in rows if r["kind"] == "line_item_extra")

    routes = [r for r in rows if r["kind"] == "route"]
    planted = [r for r in routes if r["expected"] == "review"]
    clean = [r for r in routes if r["expected"] == "auto"]
    m["planted_caught"] = f"{sum(r['actual'] == 'review' for r in planted)}/{len(planted)} " \
                          f"({', '.join(r['document_id'] + '=' + (r['actual'] or 'null') for r in planted)})"
    flags = {r["document_id"]: r for r in rows if r["kind"] == "flags"}
    m["planted_flag_correct"] = f"{sum(is_ok(flags[r['document_id']]) for r in planted if r['document_id'] in flags)}/{len(planted)}"
    false_reviews = [r["document_id"] for r in clean if r["actual"] == "review"]
    m["false_reviews"] = f"{len(false_reviews)}/{len(clean)}" + (f" ({', '.join(false_reviews)})" if false_reviews else "")

    invented = [f"{r['document_id']}.{r['field']}={r['actual']}" for r in header if str(r["invented"]) == "1"]
    m["invented_values"] = len(invented)
    m["invented_detail"] = invented

    meta = {}
    for r in rows:
        if r["kind"] == "meta":
            meta.setdefault(r["document_id"], {})[r["field"]] = r["actual"]
    m["documents"] = len(meta)
    m["documents_done"] = sum(1 for d in meta.values() if d.get("status") == "done")
    not_done = [k for k, d in meta.items() if d.get("status") != "done"]
    m["documents_not_done"] = not_done

    secs = [s for d in meta.values() if (s := _num(d.get("seconds"))) is not None]
    pages = [p for d in meta.values() if (p := _num(d.get("pages"))) is not None]
    m["seconds_per_doc_median"] = round(statistics.median(secs), 2) if secs else None
    m["seconds_per_doc_max"] = round(max(secs), 2) if secs else None
    m["pages_per_minute"] = round(sum(pages) / (sum(secs) / 60), 1) if secs and pages and sum(secs) > 0 and len(pages) == len(secs) else None

    costs = [c for d in meta.values() if (c := _num(d.get("cost_usd"))) is not None]
    m["cost_per_doc_mean_usd"] = round(statistics.mean(costs), 4) if costs else None
    m["cost_per_doc_max_usd"] = round(max(costs), 4) if costs else None
    m["cost_total_usd"] = round(sum(costs), 4) if costs else None
    m["input_tokens_total"] = int(sum(_num(d.get("input_tokens")) or 0 for d in meta.values()))
    m["output_tokens_total"] = int(sum(_num(d.get("output_tokens")) or 0 for d in meta.values()))
    m["models"] = sorted({d.get("model") for d in meta.values() if d.get("model")})
    return m
