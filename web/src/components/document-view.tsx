"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import useSWR from "swr";
import { ArrowLeft, Loader2 } from "lucide-react";

import { OutcomeBadge } from "@/components/outcome";
import { Reconciliation } from "@/components/reconciliation";
import { ReviewPanel } from "@/components/review-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { fetcher, fileUrl, pageUrl, type DocumentDetail, type ExtractedRecord } from "@/lib/api";
import { FIELD_LABEL, STATUS_TEXT, amount, dateLong, outcome, quantity, registerNote } from "@/lib/format";
import { cn } from "@/lib/utils";

const LOW = 0.8; // same threshold as the API's routing rule

function FileViewer({ doc }: { doc: DocumentDetail }) {
  const src = fileUrl(doc.id);
  // PDFs are shown as page images rendered by the API, so the original looks the same in every browser.
  const pages = doc.content_type === "application/pdf" ? Array.from({ length: doc.pages ?? 1 }, (_, i) => pageUrl(doc.id, i + 1)) : [src];
  return (
    <div className="rounded-xl bg-lighttable p-3 lg:sticky lg:top-6">
      <div className="max-h-[80vh] space-y-3 overflow-y-auto rounded-md">
        {pages.map((url, i) => (
          // eslint-disable-next-line @next/next/no-img-element -- served by our API, already sized; next/image adds nothing here
          <img
            key={url}
            src={url}
            alt={pages.length > 1 ? `Original file ${doc.filename}, page ${i + 1} of ${pages.length}` : `Original file ${doc.filename}`}
            className="mx-auto w-full rounded-md bg-card shadow-sm"
          />
        ))}
      </div>
      <a href={src} target="_blank" rel="noreferrer" className="mt-2 inline-block text-xs text-muted-foreground hover:underline">
        Open the original in a new tab
      </a>
    </div>
  );
}

function Field({ name, record, money }: { name: keyof ExtractedRecord; record: ExtractedRecord; money?: boolean }) {
  const raw = record[name] as string | number | null;
  const confidence = record.confidence[name];
  const low = confidence !== undefined && confidence < LOW;
  return (
    <div className={cn("flex items-baseline justify-between gap-3 border-b border-border py-2.5", low && "bg-review-soft -mx-2 px-2")}>
      <dt className="text-sm text-muted-foreground">{FIELD_LABEL[name]}</dt>
      <dd className="flex items-baseline gap-2 text-right">
        <span className={cn("font-medium", money && "tabular-nums")}>
          {raw === null || raw === "" ? <span className="font-normal text-muted-foreground">Not on the document</span> : money ? amount(raw as number) : raw}
        </span>
        {confidence !== undefined && (
          <span
            className={cn("w-9 text-right text-xs tabular-nums", low ? "font-semibold text-review" : "text-muted-foreground")}
            title="How sure the reader is that this matches the document"
          >
            {Math.round(confidence * 100)}%
          </span>
        )}
      </dd>
    </div>
  );
}

function RecordDetails({ record }: { record: ExtractedRecord }) {
  return (
    <>
      <section aria-label="Invoice details" className="rounded-xl border border-border bg-card px-5 pt-3 pb-4">
        <div className="flex items-baseline justify-between pt-1 pb-1">
          <h2 className="font-semibold">Details</h2>
          <span className="text-xs text-muted-foreground">How sure</span>
        </div>
        <dl className="grid gap-x-8 sm:grid-cols-2">
          <div>
            <Field name="vendor_name" record={record} />
            <Field name="invoice_number" record={record} />
            <Field name="invoice_date" record={record} />
            <Field name="due_date" record={record} />
            <Field name="po_number" record={record} />
            <Field name="currency" record={record} />
          </div>
          <div>
            <Field name="subtotal" record={record} money />
            <Field name="discount" record={record} money />
            <Field name="tax" record={record} money />
            <Field name="shipping" record={record} money />
            <Field name="total" record={record} money />
          </div>
        </dl>
      </section>

      <section aria-label="Line items" className="overflow-hidden rounded-xl border border-border bg-card">
        <h2 className="px-5 pt-4 pb-2 font-semibold">
          Line items <span className="font-normal text-muted-foreground tabular-nums">({record.line_items.length})</span>
        </h2>
        <div className="max-h-[28rem] overflow-y-auto">
          <Table>
            <TableHeader className="sticky top-0 bg-card">
              <TableRow className="hover:bg-transparent">
                <TableHead className="pl-5">Description</TableHead>
                <TableHead className="text-right">Qty</TableHead>
                <TableHead className="text-right">Unit price</TableHead>
                <TableHead className="pr-5 text-right">Amount</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {record.line_items.map((li, i) => (
                <TableRow key={i}>
                  <TableCell className="pl-5 whitespace-normal">{li.description}</TableCell>
                  <TableCell className="text-right tabular-nums">{quantity(li.quantity)}</TableCell>
                  <TableCell className="text-right tabular-nums">{amount(li.unit_price)}</TableCell>
                  <TableCell className="pr-5 text-right font-medium tabular-nums">{amount(li.amount)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </section>
    </>
  );
}

export function DocumentView() {
  const { id } = useParams<{ id: string }>();
  const { data: doc, error, mutate } = useSWR<DocumentDetail>(`/api/documents/${id}`, fetcher, {
    refreshInterval: (latest) => (latest && (latest.status === "done" || latest.status === "failed") ? 0 : 1000),
  });

  if (error) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-8">
        <BackLink />
        <p className="mt-6 text-mismatch">{error.status === 404 ? "This document doesn't exist." : `Couldn't load it: ${error.message}`}</p>
      </div>
    );
  }
  if (!doc) {
    return (
      <div className="mx-auto max-w-6xl space-y-4 px-4 py-8 sm:px-8">
        <Skeleton className="h-8 w-72" />
        <Skeleton className="h-[60vh] w-full" />
      </div>
    );
  }

  const record = doc.record;
  return (
    <div className="mx-auto max-w-[1400px] px-4 py-8 sm:px-8">
      <BackLink />
      <header className="mt-4 mb-6 flex flex-wrap items-center gap-x-4 gap-y-2">
        <h1 className="min-w-0 truncate text-2xl font-bold tracking-tight">
          {record?.vendor_name ? `${record.vendor_name} ${record.invoice_number ?? ""}` : doc.filename}
        </h1>
        <OutcomeBadge
          outcome={outcome({ status: doc.status, route: record?.route ?? null, review_status: doc.review?.status ?? null, outputs_status: doc.outputs_status })}
        />
        <p className="w-full text-sm text-muted-foreground tabular-nums">
          {doc.filename}, {doc.source === "email" ? "from the AP inbox" : doc.source === "eval" ? "test upload" : "uploaded"}{" "}
          {dateLong(doc.received_at)}
          {doc.pages ? `, ${doc.pages} ${doc.pages === 1 ? "page" : "pages"}` : ""}
          {doc.processing_seconds !== null ? `, read in ${doc.processing_seconds.toFixed(1)} s` : ""}
          {doc.usage.cost_usd !== null ? `, cost $${doc.usage.cost_usd.toFixed(3)}` : ""}
        </p>
        {doc.status === "done" && (record?.route === "auto" || doc.review?.status === "approved") && registerNote(doc.outputs_status) && (
          <p className="w-full text-sm text-review">{registerNote(doc.outputs_status)}</p>
        )}
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <FileViewer doc={doc} />
        <div className="min-w-0 space-y-5">
          {doc.status === "failed" && (
            <section className="rounded-xl border border-mismatch/40 bg-mismatch-soft p-5">
              <h2 className="font-semibold text-mismatch">This document couldn&apos;t be read</h2>
              <p className="mt-1 text-sm">{doc.error}</p>
              <p className="mt-2 text-sm text-muted-foreground">Upload it again, or enter it by hand.</p>
            </section>
          )}
          {(doc.status === "queued" || doc.status === "processing") && (
            <section className="flex items-center gap-3 rounded-xl border border-border bg-card p-5">
              <Loader2 className="size-5 animate-spin text-primary" aria-hidden />
              <div>
                <p className="font-semibold">{STATUS_TEXT[doc.status]}…</p>
                <p className="text-sm text-muted-foreground">The fields appear here as soon as it&apos;s done, usually within 10 seconds.</p>
              </div>
            </section>
          )}
          {record && (
            <>
              <ReviewPanel doc={doc} onDecided={() => mutate()} />
              <Reconciliation record={record} />
              <Tabs defaultValue="fields">
                <TabsList>
                  <TabsTrigger value="fields">Fields</TabsTrigger>
                  <TabsTrigger value="json">JSON</TabsTrigger>
                </TabsList>
                <TabsContent value="fields" className="mt-3 space-y-5">
                  <RecordDetails record={record} />
                </TabsContent>
                <TabsContent value="json" className="mt-3">
                  <pre className="max-h-[70vh] overflow-auto rounded-xl border border-border bg-card p-4 text-xs leading-relaxed">
                    {JSON.stringify(record, null, 2)}
                  </pre>
                </TabsContent>
              </Tabs>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function BackLink() {
  return (
    <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft className="size-4" aria-hidden /> All documents
    </Link>
  );
}
