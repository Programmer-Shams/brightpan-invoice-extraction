"""Document -> Claude content blocks -> Extraction.

Digital PDFs send their text layer (layout-preserving). PDFs without one (scans) are rendered to page
images; photos and receipt images are sent as images.
"""
import base64
import io

import anthropic
import pypdfium2 as pdfium
from PIL import Image, ImageOps
from pypdf import PdfReader

from . import config
from .models import Extraction

MIN_TEXT_CHARS = 50  # below this a PDF page has no usable text layer
RENDER_DPI = 200
MAX_IMAGE_SIDE = 2400
MAX_PAGES = 20  # an invoice longer than this goes to a person, not to 20+ rendered images
MAX_RENDER_PIXELS = 8_000_000  # a hostile PDF can declare a huge page; never render beyond this


def render_page(page, dpi: int) -> Image.Image:
    """Renders one PDF page at `dpi`, scaled down if the page would exceed MAX_RENDER_PIXELS."""
    width, height = page.get_size()  # in points (1/72 inch)
    scale = dpi / 72
    if width * height * scale * scale > MAX_RENDER_PIXELS:
        scale = (MAX_RENDER_PIXELS / (width * height)) ** 0.5
    try:
        return page.render(scale=scale).to_pil()
    finally:
        page.close()

SYSTEM_PROMPT = """You read supplier invoices and receipts for Brightpan Kitchen Supply's accounts payable team \
and return the values printed on the document. Brightpan is always the buyer ("Bill to"), never the vendor.

Report what is printed; never correct or complete the document. Validation code downstream compares the \
printed total with the line math, so a document whose numbers don't add up must come through exactly as printed.

- Dates as YYYY-MM-DD.
- due_date: only a due date printed on the document. If none is printed (receipts usually have none), use null. \
Do not derive one from payment terms.
- po_number: the buyer's purchase order number if printed (labels such as "PO #", "Your PO", "Ref"), else null.
- currency: the ISO 4217 code shown on the document (e.g. "TOTAL CAD" means CAD). Never assume USD; if the \
document gives no currency, use null.
- line_items: every line, across all pages, in order. description as printed (do not expand truncated text). \
If a unit price isn't printed but quantity and amount are, unit_price is amount / quantity.
- discount as a positive number. discount, tax and shipping are 0 when the document shows none (including \
"tax exempt").
- total: the grand total as printed.
- confidence: for each field, 0.0-1.0, how sure you are the value matches the document. Lower it for blurred, \
cut-off or ambiguous text, and for null values where the field may be present but unreadable."""


class ExtractionError(Exception):
    def __init__(self, message: str, usage: dict | None = None):
        super().__init__(message)
        self.usage = usage


def _image_block(img: Image.Image) -> dict:
    img = ImageOps.exif_transpose(img).convert("RGB")
    if max(img.size) > MAX_IMAGE_SIDE:
        img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                         "data": base64.standard_b64encode(buf.getvalue()).decode()}}


def prepare(data: bytes, content_type: str) -> tuple[list[dict], int, str]:
    """Returns (content blocks, page count, input mode)."""
    if content_type == "application/pdf":
        reader = PdfReader(io.BytesIO(data))
        if len(reader.pages) > MAX_PAGES:
            raise ExtractionError(f"{len(reader.pages)} pages; documents over {MAX_PAGES} pages are not read automatically")
        texts = [p.extract_text(extraction_mode="layout") or "" for p in reader.pages]
        if all(len(t.strip()) >= MIN_TEXT_CHARS for t in texts):
            body = "\n\n".join(f"--- page {i} of {len(texts)} ---\n" + "\n".join(l.rstrip() for l in t.splitlines() if l.strip())
                               for i, t in enumerate(texts, start=1))
            return [{"type": "text", "text": f"Text layer of the PDF:\n\n{body}"}], len(texts), "pdf_text"
        pdf = pdfium.PdfDocument(data)
        try:
            blocks = [_image_block(render_page(page, RENDER_DPI)) for page in pdf]
        finally:
            pdf.close()
        return blocks, len(blocks), "pdf_images"
    return [_image_block(Image.open(io.BytesIO(data)))], 1, "image"


def cost_usd(model: str, usage) -> float | None:
    p = config.PRICING.get(model)
    if p is None:
        return None
    tokens = {"input": usage.input_tokens, "output": usage.output_tokens,
              "cache_read": getattr(usage, "cache_read_input_tokens", 0) or 0,
              "cache_write": getattr(usage, "cache_creation_input_tokens", 0) or 0}
    return round(sum(tokens[k] * p[k] for k in tokens) / 1_000_000, 6)


def extract(client: anthropic.Anthropic, data: bytes, content_type: str) -> dict:
    blocks, pages, mode = prepare(data, content_type)
    response = client.beta.messages.parse(
        model=config.MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        output_config={"effort": config.EFFORT},
        output_format=Extraction,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": [*blocks, {"type": "text", "text": "Extract this document."}]}],
    )
    usage = {"model": response.model, "input_tokens": response.usage.input_tokens,
             "output_tokens": response.usage.output_tokens, "cost_usd": cost_usd(response.model, response.usage)}
    if response.stop_reason == "refusal":
        raise ExtractionError(f"model refused (category: {getattr(response.stop_details, 'category', None)})", usage)
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise ExtractionError(f"no structured output (stop_reason={response.stop_reason})", usage)
    return {"extraction": response.parsed_output, "pages": pages, "input_mode": mode, "usage": usage,
            "request_id": response._request_id}
