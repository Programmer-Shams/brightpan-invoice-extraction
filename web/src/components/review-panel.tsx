"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { decideReview, type DocumentDetail } from "@/lib/api";
import { FLAG_DETAIL, FLAG_TEXT, REVIEW_TEXT, registerNote } from "@/lib/format";
import { cn } from "@/lib/utils";

export function ReviewPanel({ doc, onDecided }: { doc: DocumentDetail; onDecided: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const record = doc.record;
  if (!record || record.route !== "review" || !doc.review) return null;

  const open = doc.review.status === "open";

  async function decide(action: "approve" | "reject") {
    setBusy(action);
    try {
      const result = await decideReview(doc.id, action, note);
      if (action === "reject") toast.success("Rejected. It stays out of the register.");
      else if (result.outputs_status === "sent") toast.success("Approved and added to the AP register.");
      else toast.warning(`Approved. ${registerNote(result.outputs_status) ?? ""}`.trim());
      onDecided();
    } catch (e) {
      toast.error(`Couldn't save the decision: ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <section aria-label="Review" className={cn("rounded-xl border p-5", open ? "border-review/40 bg-review-soft" : "border-border bg-card")}>
      <h2 className="font-semibold">{open ? "Why this needs a person" : `Review: ${REVIEW_TEXT[doc.review.status]}`}</h2>
      <ul className="mt-3 space-y-2">
        {record.flags.map((f) => (
          <li key={f} className="text-sm">
            <span className="font-semibold text-review">{FLAG_TEXT[f]}.</span>{" "}
            <span className="text-foreground/80">{FLAG_DETAIL[f]}</span>
            {f === "low_confidence" && record.checks.low_confidence_fields && (
              <span className="text-foreground/80"> Check: {record.checks.low_confidence_fields.join(", ").replaceAll("_", " ")}.</span>
            )}
            {f === "missing_required_field" && record.checks.missing_required && (
              <span className="text-foreground/80"> Missing: {record.checks.missing_required.join(", ").replaceAll("_", " ")}.</span>
            )}
          </li>
        ))}
      </ul>

      {open ? (
        <div className="mt-4 space-y-3">
          <label htmlFor="review-note" className="text-sm font-medium">
            Note for the record (optional)
          </label>
          <Textarea
            id="review-note"
            value={note}
            maxLength={1000}
            onChange={(e) => setNote(e.target.value)}
            placeholder="For example: called the vendor, the correct total is 440.00"
            className="bg-card"
          />
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => decide("approve")} disabled={busy !== null}>
              {busy === "approve" ? "Approving…" : "Approve and add to register"}
            </Button>
            <Button variant="outline" onClick={() => decide("reject")} disabled={busy !== null} className="text-mismatch">
              {busy === "reject" ? "Rejecting…" : "Reject"}
            </Button>
          </div>
        </div>
      ) : (
        doc.review.note && <p className="mt-3 text-sm text-muted-foreground">Note: {doc.review.note}</p>
      )}
    </section>
  );
}
