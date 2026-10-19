"""Validation, duplicate key and routing. Pure functions: no I/O, so they are unit-tested directly.

The extractor never corrects a document. These checks compare the printed values with the math
and raise flags; a flagged document goes to review.
"""
import re
from datetime import date

from .models import FLAGS, REQUIRED_FIELDS, Extraction, Record

# ISO 4217 codes a Brightpan supplier could plausibly bill in; anything else is treated as unreadable.
ISO_4217 = {"USD", "CAD", "EUR", "GBP", "MXN", "AUD", "JPY", "CNY", "CHF", "NZD", "SEK", "NOK", "DKK", "INR"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def valid_date(v: str | None) -> bool:
    if v is None or not DATE_RE.match(v):
        return False
    try:
        date.fromisoformat(v)
        return True
    except ValueError:
        return False


def money(v: float | None) -> float:
    return 0.0 if v is None else float(v)


def cents(v: float) -> int:
    return round(v * 100)


def within(a: float, b: float, tolerance: float) -> bool:
    """Money comparison in whole cents, so float error never turns an exact 2-cent gap into a mismatch."""
    return abs(cents(a) - cents(b)) <= cents(tolerance)


def check_totals(x: Extraction, tolerance: float) -> tuple[bool, dict]:
    """sum(line amounts) = subtotal, and subtotal - discount + tax + shipping = printed total."""
    line_sum = round(sum(money(li.amount) for li in x.line_items), 2)
    checks = {"line_sum": line_sum}
    ok = True
    if x.subtotal is not None:
        checks["line_sum_minus_subtotal"] = round(line_sum - x.subtotal, 2)
        ok &= within(line_sum, x.subtotal, tolerance)
    subtotal = x.subtotal if x.subtotal is not None else line_sum
    computed = round(subtotal - money(x.discount) + money(x.tax) + money(x.shipping), 2)
    checks["computed_total"] = computed
    if x.total is not None:
        checks["printed_minus_computed"] = round(x.total - computed, 2)
        ok &= within(x.total, computed, tolerance)
    if any(li.amount is None for li in x.line_items):
        checks["line_items_missing_amount"] = sum(li.amount is None for li in x.line_items)
        ok = False
    return ok, checks


def missing_required(x: Extraction) -> list[str]:
    missing = [f for f in REQUIRED_FIELDS if getattr(x, f) in (None, "")]
    if x.invoice_date is not None and not valid_date(x.invoice_date):
        missing.append("invoice_date (not YYYY-MM-DD)")
    if x.due_date is not None and not valid_date(x.due_date):
        missing.append("due_date (not YYYY-MM-DD)")
    if x.currency is not None and x.currency not in ISO_4217:
        missing.append(f"currency ({x.currency!r} not ISO 4217)")
    return missing


def duplicate_key(vendor_name: str | None, invoice_number: str | None) -> str | None:
    """Same vendor + same invoice number, ignoring case, spacing and punctuation ("FM-10421" == "FM 10421")."""
    if not vendor_name or not invoice_number:
        return None
    norm = lambda s: re.sub(r"[^0-9a-z]", "", s.casefold())
    return f"{norm(vendor_name)}|{norm(invoice_number)}"


def build_record(x: Extraction, *, is_duplicate: bool, threshold: float, tolerance: float) -> Record:
    flags, checks = [], {}
    totals_ok, checks["totals"] = check_totals(x, tolerance)
    if not totals_ok:
        flags.append("totals_mismatch")
    if is_duplicate:
        flags.append("duplicate_invoice")
    confidence = x.confidence.model_dump()
    low = sorted(f for f in REQUIRED_FIELDS if confidence.get(f, 0.0) < threshold)
    if low:
        flags.append("low_confidence")
        checks["low_confidence_fields"] = low
    missing = missing_required(x)
    if missing:
        flags.append("missing_required_field")
        checks["missing_required"] = missing
    assert all(f in FLAGS for f in flags)
    data = x.model_dump(exclude={"confidence"})
    return Record(**data, confidence=confidence, flags=flags, route="review" if flags else "auto", checks=checks)
