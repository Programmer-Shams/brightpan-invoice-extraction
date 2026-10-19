// Types mirror app/main.py responses. All requests go through the /api proxy (src/app/api/[...path]).

export type Status = "queued" | "processing" | "done" | "failed";
export type ReviewStatus = "open" | "approved" | "rejected";
export type Flag = "totals_mismatch" | "duplicate_invoice" | "low_confidence" | "missing_required_field";

export interface DocumentSummary {
  id: string;
  filename: string;
  content_type: string;
  source: string;
  status: Status;
  pages: number | null;
  error: string | null;
  received_at: string;
  processing_seconds: number | null;
  vendor_name: string | null;
  invoice_number: string | null;
  currency: string | null;
  total: number | null;
  route: "auto" | "review" | null;
  flags: Flag[];
  review_status: ReviewStatus | null;
  outputs_status: string | null;
  cost_usd: number | null;
  review_reasons?: Flag[];
}

export interface LineItem {
  description: string;
  quantity: number | null;
  unit_price: number | null;
  amount: number | null;
}

export interface Totals {
  line_sum: number;
  computed_total: number;
  printed_minus_computed?: number;
  line_sum_minus_subtotal?: number;
  line_items_missing_amount?: number;
}

export interface ExtractedRecord {
  vendor_name: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  due_date: string | null;
  currency: string | null;
  po_number: string | null;
  line_items: LineItem[];
  subtotal: number | null;
  discount: number | null;
  tax: number | null;
  shipping: number | null;
  total: number | null;
  confidence: Record<string, number>;
  flags: Flag[];
  route: "auto" | "review";
  checks: { totals?: Totals; low_confidence_fields?: string[]; missing_required?: string[] };
}

export interface DocumentDetail {
  id: string;
  filename: string;
  content_type: string;
  source: string;
  status: Status;
  pages: number | null;
  error: string | null;
  received_at: string;
  finished_at: string | null;
  processing_seconds: number | null;
  record: ExtractedRecord | null;
  input_mode: string | null;
  outputs_status: string | null;
  outputs_gave_up: boolean;
  review: { status: ReviewStatus; note: string | null } | null;
  usage: { model: string | null; input_tokens: number | null; output_tokens: number | null; cost_usd: number | null };
}

export interface ResultsDocument {
  document_id: string;
  format: string;
  header_correct: number;
  header_total: number;
  lines_correct: number;
  lines_total: number;
  mismatches: { field: string; expected: string; actual: string }[];
  route_expected?: string;
  route_actual?: string;
  flags_expected?: string;
  flags_actual?: string;
  seconds?: string;
  cost_usd?: string;
  pages?: string;
  status?: string;
}

export interface Results {
  metrics: Record<string, unknown> & {
    field_accuracy: string;
    field_accuracy_by_format: Record<string, string>;
    field_accuracy_by_field: Record<string, string>;
    line_item_accuracy: string;
    extra_line_items: number;
    planted_caught: string;
    planted_flag_correct: string;
    false_reviews: string;
    invented_values: number;
    seconds_per_doc_median: number | null;
    seconds_per_doc_max: number | null;
    pages_per_minute: number | null;
    cost_per_doc_mean_usd: number | null;
    cost_total_usd: number | null;
    documents: number;
    documents_done: number;
    models: string[];
  };
  header_fields: string[];
  documents: ResultsDocument[];
  run_at: string | null;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function parse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {}
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const fetcher = <T,>(url: string) => fetch(url, { cache: "no-store" }).then((r) => parse<T>(r));

export async function uploadDocument(file: File): Promise<{ id: string; status: Status }> {
  const form = new FormData();
  form.append("file", file);
  form.append("source", "upload");
  return parse(await fetch("/api/documents", { method: "POST", body: form }));
}

export async function decideReview(id: string, action: "approve" | "reject", note: string) {
  return parse<{ id: string; review_status: ReviewStatus; outputs_status: string | null }>(
    await fetch(`/api/review/${id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, note: note.trim() || null }),
    }),
  );
}

export const fileUrl = (id: string) => `/api/documents/${id}/file`;
export const pageUrl = (id: string, page: number) => `/api/documents/${id}/pages/${page}`;

/** "200/200 (100.0%)" -> {n: 200, d: 200} */
export function ratio(text: string): { n: number; d: number } {
  const m = /^(\d+)\/(\d+)/.exec(text);
  return m ? { n: Number(m[1]), d: Number(m[2]) } : { n: 0, d: 0 };
}
