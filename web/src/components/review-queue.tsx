"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";

import { Skeleton } from "@/components/ui/skeleton";
import { fetcher, type DocumentSummary, type ReviewStatus } from "@/lib/api";
import { FLAG_DETAIL, FLAG_TEXT, REVIEW_TEXT, amount, received } from "@/lib/format";
import { cn } from "@/lib/utils";

const TABS: ReviewStatus[] = ["open", "approved", "rejected"];

export function ReviewQueue() {
  const [tab, setTab] = useState<ReviewStatus>("open");
  const { data, error } = useSWR<DocumentSummary[]>(`/api/review?status=${tab}`, fetcher, { refreshInterval: 5000 });

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Review queue</h1>
        <p className="mt-1 text-muted-foreground">
          Documents the checks didn&apos;t pass. Nothing here reaches the AP register until someone approves it.
        </p>
      </header>

      <div role="tablist" aria-label="Review status" className="mb-4 inline-flex rounded-lg bg-muted p-1">
        {TABS.map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors",
              tab === t && "bg-card text-foreground shadow-sm",
            )}
          >
            {REVIEW_TEXT[t]}
          </button>
        ))}
      </div>

      {error ? (
        <p className="text-sm text-mismatch">Couldn&apos;t load the queue: {error.message}</p>
      ) : !data ? (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : data.length === 0 ? (
        <div className="rounded-xl border border-border bg-card p-10 text-center">
          <p className="font-semibold">{tab === "open" ? "Nothing waiting for review" : `No ${REVIEW_TEXT[tab].toLowerCase()} documents yet`}</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {tab === "open" ? "Documents with a wrong total, a duplicate number or unreadable details will appear here." : "Decisions made in the open queue show up here."}
          </p>
        </div>
      ) : (
        <ul className="space-y-3">
          {data.map((d) => (
            <li key={d.id}>
              <Link
                href={`/review/${d.id}`}
                className="block rounded-xl border border-border bg-card p-5 transition-colors hover:border-primary/50"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="font-semibold">
                    {d.vendor_name ?? d.filename} <span className="font-normal text-muted-foreground tabular-nums">{d.invoice_number}</span>
                  </p>
                  <p className="font-semibold tabular-nums">
                    {d.total !== null && (
                      <>
                        <span className="mr-1 text-xs font-normal text-muted-foreground">{d.currency}</span>
                        {amount(d.total)}
                      </>
                    )}
                  </p>
                </div>
                <ul className="mt-2 space-y-1">
                  {(d.review_reasons ?? d.flags).map((f) => (
                    <li key={f} className="text-sm">
                      <span className="font-semibold text-review">{FLAG_TEXT[f]}.</span>{" "}
                      <span className="text-muted-foreground">{FLAG_DETAIL[f]}</span>
                    </li>
                  ))}
                </ul>
                <p className="mt-3 text-xs text-muted-foreground">
                  {d.filename}, {d.source === "email" ? "from the AP inbox" : "uploaded"} {received(d.received_at)}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
