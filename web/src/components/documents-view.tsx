"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { FileImage, FileText, Mail } from "lucide-react";

import { OutcomeBadge } from "@/components/outcome";
import { UploadZone } from "@/components/upload-zone";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fetcher, type DocumentSummary } from "@/lib/api";
import { FLAG_TEXT, amount, outcome, received } from "@/lib/format";

export function DocumentsView() {
  const router = useRouter();
  const { data, error, mutate } = useSWR<DocumentSummary[]>("/api/documents?limit=200", fetcher, {
    // Poll quickly while something is being read, slowly otherwise.
    refreshInterval: (latest) => (latest?.some((d) => d.status === "queued" || d.status === "processing") ? 1500 : 8000),
  });

  const counts = {
    total: data?.length ?? 0,
    register: data?.filter((d) => outcome(d) === "register" || outcome(d) === "approved").length ?? 0,
    review: data?.filter((d) => outcome(d) === "review").length ?? 0,
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Supplier documents</h1>
          <p className="mt-1 text-muted-foreground">Everything received by upload or from the AP inbox, newest first.</p>
        </div>
        {data && data.length > 0 && (
          <p className="text-sm text-muted-foreground tabular-nums">
            {counts.total} received, {counts.register} filed, {counts.review} waiting for review
          </p>
        )}
      </header>

      <UploadZone onUploaded={() => mutate()} />

      <section aria-label="Documents" className="mt-6 overflow-hidden rounded-xl border border-border bg-card">
        {error ? (
          <p className="p-6 text-sm text-mismatch">Couldn&apos;t load documents: {error.message}</p>
        ) : !data ? (
          <div className="space-y-3 p-6">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        ) : data.length === 0 ? (
          <div className="p-10 text-center">
            <p className="font-semibold">No documents yet</p>
            <p className="mt-1 text-sm text-muted-foreground">Drop a PDF or a photo of an invoice above to see it read.</p>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="pl-5">File</TableHead>
                <TableHead>Vendor</TableHead>
                <TableHead>Invoice</TableHead>
                <TableHead className="text-right">Total</TableHead>
                <TableHead>Outcome</TableHead>
                <TableHead className="pr-5 text-right">Received</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((d) => {
                const href = `/documents/${d.id}`;
                const Icon = d.source === "email" ? Mail : d.content_type === "application/pdf" ? FileText : FileImage;
                return (
                  <TableRow key={d.id} className="cursor-pointer" onClick={() => router.push(href)}>
                    <TableCell className="pl-5">
                      <Link href={href} className="flex items-center gap-2 font-medium hover:underline" onClick={(e) => e.stopPropagation()}>
                        <Icon className="size-4 shrink-0 text-steel" aria-label={d.source === "email" ? "From email" : undefined} />
                        <span className="max-w-56 truncate">{d.filename}</span>
                      </Link>
                    </TableCell>
                    <TableCell className="max-w-48 truncate">{d.vendor_name ?? <span className="text-muted-foreground">—</span>}</TableCell>
                    <TableCell className="tabular-nums">{d.invoice_number ?? <span className="text-muted-foreground">—</span>}</TableCell>
                    <TableCell className="text-right font-medium tabular-nums">
                      {d.total !== null ? (
                        <>
                          <span className="mr-1 text-xs font-normal text-muted-foreground">{d.currency}</span>
                          {amount(d.total)}
                        </>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <OutcomeBadge outcome={outcome(d)} />
                        {outcome(d) === "review" && (
                          <span className="text-xs text-muted-foreground">{d.flags.map((f) => FLAG_TEXT[f]).join(", ")}</span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="pr-5 text-right text-sm text-muted-foreground tabular-nums whitespace-nowrap">
                      {received(d.received_at)}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </section>
    </div>
  );
}
