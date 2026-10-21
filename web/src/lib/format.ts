import type { DocumentSummary, Flag, ReviewStatus, Status } from "./api";

export function amount(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function money(currency: string | null | undefined, value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${currency ?? ""} ${amount(value)}`.trim();
}

export function quantity(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("en-US", { maximumFractionDigits: 3 });
}

export function received(iso: string): string {
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function dateLong(iso: string): string {
  return new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export const STATUS_TEXT: Record<Status, string> = {
  queued: "Waiting",
  processing: "Reading",
  done: "Read",
  failed: "Couldn't read",
};

export const FLAG_TEXT: Record<Flag, string> = {
  totals_mismatch: "Totals don't add up",
  duplicate_invoice: "Already received",
  low_confidence: "Hard to read",
  missing_required_field: "Missing details",
};

export const FLAG_DETAIL: Record<Flag, string> = {
  totals_mismatch: "The printed total doesn't match the line items, discount, tax and shipping.",
  duplicate_invoice: "An invoice with this vendor and invoice number is already on file.",
  low_confidence: "Some required details were hard to read, so a person should confirm them.",
  missing_required_field: "A required detail is missing or not in the expected format.",
};

export const FIELD_LABEL: Record<string, string> = {
  vendor_name: "Vendor",
  invoice_number: "Invoice number",
  invoice_date: "Invoice date",
  due_date: "Due date",
  currency: "Currency",
  po_number: "PO number",
  line_items: "Line items",
  subtotal: "Subtotal",
  discount: "Discount",
  tax: "Tax",
  shipping: "Shipping",
  total: "Total",
};

export type Outcome = "reading" | "register" | "passed" | "review" | "approved" | "rejected" | "failed";

export function outcome(doc: Pick<DocumentSummary, "status" | "route" | "review_status" | "outputs_status">): Outcome {
  if (doc.status === "failed") return "failed";
  if (doc.status !== "done") return "reading";
  if (doc.review_status === "approved") return "approved";
  if (doc.review_status === "rejected") return "rejected";
  if (doc.route === "review") return "review";
  // "In AP register" only once the register update actually went out (the outputs webhook confirmed it).
  return doc.outputs_status === "sent" ? "register" : "passed";
}

/** What happened to the AP register update, in words; null when there is nothing to say. */
export function registerNote(outputsStatus: string | null, gaveUp = false): string | null {
  if (gaveUp) return "The AP register update failed 5 times and is no longer retried. Check the n8n outputs workflow.";
  if (!outputsStatus || outputsStatus === "sending" || outputsStatus === "in_flight") return "The AP register update is still being sent.";
  if (outputsStatus === "sent") return null;
  if (outputsStatus === "skipped:eval upload") return "Test upload: not added to the AP register.";
  if (outputsStatus.startsWith("skipped:")) return "The AP register isn't connected, so it wasn't added.";
  return "The AP register update failed; it is retried automatically.";
}

export const OUTCOME_TEXT: Record<Outcome, string> = {
  reading: "Reading",
  register: "In AP register",
  passed: "Passed checks",
  review: "Needs review",
  approved: "Approved",
  rejected: "Rejected",
  failed: "Couldn't read",
};

export const REVIEW_TEXT: Record<ReviewStatus, string> = { open: "Open", approved: "Approved", rejected: "Rejected" };
