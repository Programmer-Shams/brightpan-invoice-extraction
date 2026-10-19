"""Sends each processed document to Demo 4's n8n: auto -> a row in the AP register sheet, review -> Slack.

The payload is fully shaped here (sheet row + Slack message) so the n8n workflow only routes it.
Eval uploads are not sent unless NOTIFY_EVAL=1, so eval runs don't fill the register or the channel.
"""
import logging

import httpx

from . import config

log = logging.getLogger("notify")
WEBHOOK_HEADER = "X-Brightpan-Signature"  # checked by the webhook's Header Auth credential in n8n

FLAG_TEXT = {
    "totals_mismatch": "totals don't add up",
    "duplicate_invoice": "duplicate of an invoice already received",
    "low_confidence": "low confidence on a required field",
    "missing_required_field": "missing or invalid required field",
}


def cell(v) -> str:
    """Text for the register. The n8n Sheets step writes with cellFormat RAW, so Sheets stores values literally and
    never evaluates a formula; no apostrophe prefix is needed (with RAW it would be stored as a visible character)."""
    return "" if v is None else str(v)


def slack_escape(v) -> str:
    """Slack treats & < > as control characters (links, mentions); document text must not inject them."""
    return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def money(currency: str | None, v: float | None) -> str:
    return "—" if v is None else f"{currency or ''} {v:,.2f}".strip()


def sheet_row(doc: dict, r: dict) -> dict:
    return {
        "Received": doc["received_at"].isoformat(timespec="seconds"),
        "Vendor": cell(r["vendor_name"]), "Invoice #": cell(r["invoice_number"]),
        "Invoice date": cell(r["invoice_date"]), "Due date": cell(r["due_date"]),
        "Currency": cell(r["currency"]), "PO #": cell(r["po_number"]),
        "Subtotal": r["subtotal"], "Discount": r["discount"], "Tax": r["tax"], "Shipping": r["shipping"],
        "Total": r["total"], "Line items": len(r["line_items"]),
        "Source": cell(doc["source"]), "File": cell(doc["filename"]),
        "Link": f"{config.FRONTEND_URL}/documents/{doc['id']}", "Document ID": str(doc["id"]),
    }


def slack_message(doc: dict, r: dict) -> dict:
    t = r.get("checks", {}).get("totals", {})
    cur = slack_escape(r["currency"]) if r["currency"] else None
    reasons = []
    for f in r["flags"]:
        line = FLAG_TEXT.get(f, f)
        if f == "totals_mismatch" and "computed_total" in t:
            line += f" (printed {money(cur, r['total'])}, lines add up to {money(cur, t['computed_total'])})"
        if f == "missing_required_field":
            line += f" ({slack_escape(', '.join(r.get('checks', {}).get('missing_required', [])))})"
        if f == "low_confidence":
            line += f" ({', '.join(r.get('checks', {}).get('low_confidence_fields', []))})"
        reasons.append(f"• {line}")
    title = slack_escape(f"{r['vendor_name'] or 'Unknown vendor'} {r['invoice_number'] or ''}".strip())
    link = f"{config.FRONTEND_URL}/review/{doc['id']}"
    text = (f":mag: *Invoice needs review:* {title}, {money(cur, r['total'])}\n"
            + "\n".join(reasons) + f"\nFile: {slack_escape(doc['filename'])} ({slack_escape(doc['source'])})  <{link}|Open in review queue>")
    return {"text": text}


def send(doc: dict, record: dict, event: str = "document.processed") -> str:
    """Auto documents and approved review items go to the AP register; new review items go to Slack.
    Returns the outcome stored on the extraction: sent | skipped:<why> | failed:<why>."""
    if not config.N8N_OUTPUTS_WEBHOOK_URL or not config.OUTPUTS_WEBHOOK_SECRET:
        return "skipped:no webhook configured"
    if doc["source"] == "eval" and not config.NOTIFY_EVAL:
        return "skipped:eval upload"
    to_register = record["route"] == "auto" or event == "review.approved"
    payload = {"event": event, "document_id": str(doc["id"]), "route": record["route"], "flags": record["flags"],
               "destination": "register" if to_register else "slack"}
    if to_register:
        payload["sheet_row"] = sheet_row(doc, record)
    else:
        payload["slack"] = slack_message(doc, record)
    try:
        # The webhook answers after the Sheet / Slack step ran, so a failure there comes back as an error here.
        httpx.post(config.N8N_OUTPUTS_WEBHOOK_URL, json=payload, timeout=30,
                   headers={WEBHOOK_HEADER: config.OUTPUTS_WEBHOOK_SECRET}).raise_for_status()
        return "sent"
    except httpx.HTTPError as e:
        log.warning("%s output webhook failed: %s", doc["id"], e)
        return f"failed:{type(e).__name__}"
