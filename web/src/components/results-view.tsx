"use client";

import useSWR from "swr";
import { Check, X } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { fetcher, ratio, type Results } from "@/lib/api";
import { FIELD_LABEL } from "@/lib/format";
import { cn } from "@/lib/utils";

const FORMAT_LABEL: Record<string, string> = {
  digital: "Digital PDFs",
  multipage: "Two-page PDF",
  scan: "Scanned PDFs",
  photo: "Phone photos",
  receipt: "Receipts",
};

function pct(text: string) {
  const { n, d } = ratio(text);
  return d ? (100 * n) / d : 0;
}

function Bar({ label, text, unit }: { label: string; text: string; unit: string }) {
  const { n, d } = ratio(text);
  const value = pct(text);
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="grid grid-cols-[9rem_1fr_4.5rem] items-center gap-3 rounded-md px-1 py-1.5 outline-none hover:bg-muted focus-visible:bg-muted" tabIndex={0}>
          <span className="truncate text-sm">{label}</span>
          <div className="h-2.5 rounded-full bg-muted" role="img" aria-label={`${label}: ${n} of ${d} ${unit} correct`}>
            <div className="h-full rounded-full bg-primary" style={{ width: `${value}%` }} />
          </div>
          <span className="text-right text-sm font-medium tabular-nums">{value === 100 ? "100%" : `${value.toFixed(1)}%`}</span>
        </div>
      </TooltipTrigger>
      <TooltipContent>
        {n} of {d} {unit} correct
      </TooltipContent>
    </Tooltip>
  );
}

function Figure({ value, label, detail }: { value: string; label: string; detail?: string }) {
  return (
    <div className="px-5 py-4">
      <div className="text-3xl font-bold tracking-tight tabular-nums">{value}</div>
      <div className="mt-1 text-sm font-medium">{label}</div>
      {detail && <div className="text-xs text-muted-foreground">{detail}</div>}
    </div>
  );
}

function Pass({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <span className={cn("inline-flex items-center gap-1 tabular-nums", ok ? "text-balanced" : "text-mismatch")}>
      {ok ? <Check className="size-3.5" aria-label="correct" /> : <X className="size-3.5" aria-label="wrong" />}
      {children}
    </span>
  );
}

export function ResultsView() {
  const { data, error } = useSWR<Results>("/api/results", fetcher);

  if (error) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-8 sm:px-8">
        <h1 className="text-2xl font-bold tracking-tight">Test results</h1>
        <p className="mt-4 text-mismatch">
          {error.status === 404 ? "No test run yet. Run eval/run_eval.py to measure the system." : `Couldn't load results: ${error.message}`}
        </p>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="mx-auto max-w-5xl space-y-4 px-4 py-8 sm:px-8">
        <Skeleton className="h-8 w-60" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const m = data.metrics;
  const fields = ratio(m.field_accuracy);
  const lines = ratio(m.line_item_accuracy);
  const planted = ratio(m.planted_caught);
  const falseReviews = ratio(m.false_reviews);
  const mismatched = data.documents.filter((d) => d.mismatches.length > 0);
  const runDate = data.run_at
    ? new Date(data.run_at).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })
    : "an unrecorded date";

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Test results</h1>
        <p className="mt-1 max-w-[70ch] text-muted-foreground">
          {m.documents} test documents run through the live system on {runDate}: digital PDFs, a two-page invoice, scans, phone
          photos and receipts, each compared field by field with its answer key. Scoring is strict, so &ldquo;Inc.&rdquo; and
          &ldquo;Inc&rdquo; count as different.
        </p>
      </header>

      <section aria-label="Headline results" className="grid grid-cols-1 gap-px overflow-hidden rounded-xl border border-border bg-border min-[420px]:grid-cols-2 md:grid-cols-3 [&>*]:bg-card">
        <Figure value={`${fields.n}/${fields.d}`} label="Fields correct" detail="vendor, number, dates, currency, PO, amounts" />
        <Figure value={`${lines.n}/${lines.d}`} label="Line items correct" detail="description, qty, price and amount all right" />
        <Figure value={`${planted.n}/${planted.d}`} label="Planted errors caught" detail="wrong total, duplicate invoice" />
        <Figure value={`${falseReviews.n}`} label="Clean ones sent to review" detail={`out of ${falseReviews.d}`} />
        <Figure value={`${m.seconds_per_doc_median ?? "—"} s`} label="Per document" detail={`median, slowest ${m.seconds_per_doc_max ?? "—"} s, ${m.pages_per_minute ?? "—"} pages a minute`} />
        <Figure
          value={m.cost_per_doc_mean_usd !== null ? `$${m.cost_per_doc_mean_usd.toFixed(3)}` : "—"}
          label="Cost per document"
          detail={`${m.invented_values} invented values`}
        />
      </section>

      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <section className="rounded-xl border border-border bg-card p-5">
          <h2 className="mb-3 font-semibold">Fields correct, by kind of document</h2>
          {Object.entries(m.field_accuracy_by_format).map(([k, v]) => (
            <Bar key={k} label={FORMAT_LABEL[k] ?? k} text={v} unit="fields" />
          ))}
          <h2 className="mt-6 mb-3 font-semibold">Line items correct</h2>
          <Bar label="All documents" text={m.line_item_accuracy} unit="line items" />
        </section>
        <section className="rounded-xl border border-border bg-card p-5">
          <h2 className="mb-3 font-semibold">Fields correct, by field</h2>
          {Object.entries(m.field_accuracy_by_field).map(([k, v]) => (
            <Bar key={k} label={FIELD_LABEL[k] ?? k} text={v} unit="documents" />
          ))}
        </section>
      </div>

      {mismatched.length > 0 && (
        <section className="mt-6 rounded-xl border border-review/40 bg-review-soft p-5">
          <h2 className="font-semibold">What didn&apos;t match</h2>
          <ul className="mt-3 space-y-3">
            {mismatched.flatMap((d) =>
              d.mismatches.map((x) => (
                <li key={`${d.document_id}-${x.field}`} className="text-sm">
                  <span className="font-semibold">
                    {d.document_id}, {x.field}
                  </span>
                  <div className="mt-1 grid gap-1 sm:grid-cols-[6rem_1fr]">
                    <span className="text-muted-foreground">Answer key</span>
                    <span className="tabular-nums">{x.expected || "(empty)"}</span>
                    <span className="text-muted-foreground">Read as</span>
                    <span className="tabular-nums">{x.actual || "(empty)"}</span>
                  </div>
                </li>
              )),
            )}
          </ul>
        </section>
      )}

      <section aria-label="Every document" className="mt-6 overflow-hidden rounded-xl border border-border bg-card">
        <h2 className="px-5 pt-4 pb-2 font-semibold">Every document</h2>
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="pl-5">Document</TableHead>
              <TableHead>Kind</TableHead>
              <TableHead className="text-right">Fields</TableHead>
              <TableHead className="text-right">Line items</TableHead>
              <TableHead>Sent to</TableHead>
              <TableHead className="text-right">Seconds</TableHead>
              <TableHead className="pr-5 text-right">Cost</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.documents.map((d) => {
              const routeOk = d.route_expected === d.route_actual;
              return (
                <TableRow key={d.document_id}>
                  <TableCell className="pl-5 font-medium">{d.document_id}</TableCell>
                  <TableCell className="text-muted-foreground">{FORMAT_LABEL[d.format] ?? d.format}</TableCell>
                  <TableCell className="text-right">
                    <Pass ok={d.header_correct === d.header_total}>
                      {d.header_correct}/{d.header_total}
                    </Pass>
                  </TableCell>
                  <TableCell className="text-right">
                    <Pass ok={d.lines_correct === d.lines_total}>
                      {d.lines_correct}/{d.lines_total}
                    </Pass>
                  </TableCell>
                  <TableCell>
                    <Pass ok={routeOk}>
                      {d.route_actual === "review" ? "Review" : d.route_actual === "auto" ? "Register" : "—"}
                      {d.route_actual === "review" && d.flags_actual ? ` (${d.flags_actual.replaceAll("_", " ")})` : ""}
                    </Pass>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{d.seconds ? Number(d.seconds).toFixed(1) : "—"}</TableCell>
                  <TableCell className="pr-5 text-right tabular-nums">{d.cost_usd ? `$${Number(d.cost_usd).toFixed(3)}` : "—"}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </section>
      <p className="mt-3 text-xs text-muted-foreground">
        Model {m.models.join(", ")}. Seconds are measured from upload to finished. Cost comes from the token counts the API returns.
      </p>
    </div>
  );
}
