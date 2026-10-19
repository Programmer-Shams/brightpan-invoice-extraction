import { Loader2 } from "lucide-react";

import { OUTCOME_TEXT, type Outcome } from "@/lib/format";
import { cn } from "@/lib/utils";

const STYLE: Record<Outcome, string> = {
  reading: "bg-muted text-muted-foreground",
  register: "bg-balanced-soft text-balanced",
  review: "bg-review-soft text-review",
  approved: "bg-balanced-soft text-balanced",
  rejected: "bg-mismatch-soft text-mismatch",
  failed: "bg-mismatch-soft text-mismatch",
};

export function OutcomeBadge({ outcome, className }: { outcome: Outcome; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-semibold whitespace-nowrap",
        STYLE[outcome],
        className,
      )}
    >
      {outcome === "reading" && <Loader2 className="size-3 animate-spin" aria-hidden />}
      {OUTCOME_TEXT[outcome]}
    </span>
  );
}
