import { Check, X } from "lucide-react";

import type { ExtractedRecord } from "@/lib/api";
import { amount } from "@/lib/format";
import { cn } from "@/lib/utils";

const TOLERANCE = 0.02; // same as app/config.py

function Term({ op, label, value, strong }: { op?: string; label: string; value: number; strong?: boolean }) {
  return (
    <div>
      <div className={cn("text-xl tabular-nums whitespace-nowrap sm:text-2xl", strong ? "font-bold" : "font-medium")}>
        {op && <span className="mr-1.5 font-normal text-steel" aria-label={OP_NAME[op]}>{op}</span>}
        {amount(value)}
      </div>
      <div className={cn("mt-1 text-xs text-muted-foreground", op && "pl-5")}>{label}</div>
    </div>
  );
}

const OP_NAME: Record<string, string> = { "−": "minus", "+": "plus" };

/** The money check, laid out as the sum it is: subtotal − discount + tax + shipping, against the printed total. */
export function Reconciliation({ record }: { record: ExtractedRecord }) {
  const t = record.checks.totals;
  if (!t) return null;
  const subtotal = record.subtotal ?? t.line_sum;
  // The verdict is the server's (validate.py); the differences here are only for display.
  const balanced = !record.flags.includes("totals_mismatch");
  const missingAmounts = t.line_items_missing_amount ?? 0;
  const linesOk = missingAmounts === 0 && Math.abs(t.line_sum_minus_subtotal ?? 0) <= TOLERANCE;
  const gap = t.printed_minus_computed ?? null;
  const cur = record.currency ?? "";

  return (
    <section
      aria-label="Money check"
      className={cn(
        "rounded-xl border-l-4 bg-card p-5 shadow-[0_0_0_1px_var(--border)]",
        balanced ? "border-l-balanced" : "border-l-mismatch",
      )}
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Money check</h2>
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-sm font-semibold",
            balanced ? "bg-balanced-soft text-balanced" : "bg-mismatch-soft text-mismatch",
          )}
        >
          {balanced ? <Check className="size-4" aria-hidden /> : <X className="size-4" aria-hidden />}
          {balanced
            ? "Adds up"
            : gap !== null && Math.abs(gap) > TOLERANCE
              ? `Printed total is ${gap > 0 ? "over" : "under"} by ${cur} ${amount(Math.abs(gap))}`
              : missingAmounts > 0
                ? `${missingAmounts} line ${missingAmounts === 1 ? "item has" : "items have"} no amount`
                : "Line items don't match the subtotal"}
        </span>
      </div>

      <div className="flex flex-wrap items-end gap-x-5 gap-y-3">
        <Term label="Subtotal" value={subtotal} />
        <Term op="−" label="Discount" value={record.discount ?? 0} />
        <Term op="+" label="Tax" value={record.tax ?? 0} />
        <Term op="+" label="Shipping" value={record.shipping ?? 0} />
      </div>

      <div className="mt-4 flex flex-wrap items-stretch gap-3 border-t border-border pt-4">
        <div className="rounded-lg bg-muted px-4 py-2">
          <div className="text-xl font-bold tabular-nums sm:text-2xl">{amount(t.computed_total)}</div>
          <div className="mt-1 text-xs text-muted-foreground">Should be</div>
        </div>
        {record.total !== null && (
          <div className={cn("rounded-lg px-4 py-2", balanced ? "bg-balanced-soft" : "bg-mismatch-soft")}>
            <div className={cn("text-xl font-bold tabular-nums sm:text-2xl", balanced ? "text-balanced" : "text-mismatch")}>
              {amount(record.total)}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">Printed total</div>
          </div>
        )}
      </div>

      <p className={cn("mt-4 flex items-center gap-1.5 text-sm", linesOk ? "text-muted-foreground" : "text-mismatch")}>
        {linesOk ? <Check className="size-4 text-balanced" aria-hidden /> : <X className="size-4" aria-hidden />}
        {record.line_items.length} line {record.line_items.length === 1 ? "item adds" : "items add"} up to {cur} {amount(t.line_sum)}
        {record.subtotal !== null && (linesOk ? ", same as the subtotal" : `, but the subtotal says ${cur} ${amount(record.subtotal)}`)}
      </p>
    </section>
  );
}
