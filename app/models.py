"""Pydantic models: what Claude returns (Extraction) and the stored record (Record, the BUILD_SPEC schema)."""
from typing import Literal

from pydantic import BaseModel, Field

FLAGS = ("totals_mismatch", "duplicate_invoice", "low_confidence", "missing_required_field")
REQUIRED_FIELDS = ("vendor_name", "invoice_number", "invoice_date", "currency", "total")


class LineItem(BaseModel):
    description: str
    quantity: float | None
    unit_price: float | None
    amount: float | None


class Confidence(BaseModel):
    vendor_name: float
    invoice_number: float
    invoice_date: float
    due_date: float
    currency: float
    po_number: float
    line_items: float
    subtotal: float
    discount: float
    tax: float
    shipping: float
    total: float


class Extraction(BaseModel):
    """Exactly what the model reads off the document. Nothing here is computed or corrected."""
    vendor_name: str | None
    invoice_number: str | None
    invoice_date: str | None = Field(description="YYYY-MM-DD")
    due_date: str | None = Field(description="YYYY-MM-DD, or null if no due date is printed")
    currency: str | None = Field(description="ISO 4217 code, e.g. USD, CAD")
    po_number: str | None
    line_items: list[LineItem]
    subtotal: float | None
    discount: float | None
    tax: float | None
    shipping: float | None
    total: float | None
    confidence: Confidence


class Record(BaseModel):
    vendor_name: str | None
    invoice_number: str | None
    invoice_date: str | None
    due_date: str | None
    currency: str | None
    po_number: str | None
    line_items: list[LineItem]
    subtotal: float | None
    discount: float | None
    tax: float | None
    shipping: float | None
    total: float | None
    confidence: dict[str, float]
    flags: list[str]
    route: Literal["auto", "review"]
    checks: dict = Field(default_factory=dict, description="validation details: computed sums and differences")
