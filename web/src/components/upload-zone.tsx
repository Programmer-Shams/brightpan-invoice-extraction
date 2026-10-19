"use client";

import { useRef, useState } from "react";
import { Upload } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { uploadDocument } from "@/lib/api";
import { cn } from "@/lib/utils";

const ACCEPT = "application/pdf,image/jpeg,image/png";
const ACCEPTED = new Set(ACCEPT.split(","));

export function UploadZone({ onUploaded }: { onUploaded: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(0);

  async function send(files: FileList | File[]) {
    const list = Array.from(files);
    const skipped = list.filter((f) => !ACCEPTED.has(f.type));
    const valid = list.filter((f) => ACCEPTED.has(f.type));
    if (skipped.length) toast.error(`Skipped ${skipped.map((f) => f.name).join(", ")}: only PDF, JPEG and PNG files can be read.`);
    setBusy((n) => n + valid.length);
    await Promise.all(
      valid.map(async (file) => {
        try {
          await uploadDocument(file);
          toast.success(`${file.name} uploaded. Reading it now.`);
        } catch (e) {
          toast.error(`${file.name} wasn't uploaded: ${(e as Error).message}`);
        } finally {
          setBusy((n) => n - 1);
          onUploaded();
        }
      }),
    );
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        if (e.dataTransfer.files.length) send(e.dataTransfer.files);
      }}
      className={cn(
        "flex flex-col items-start gap-4 rounded-xl border-2 border-dashed border-input bg-card px-6 py-6 transition-colors sm:flex-row sm:items-center",
        over && "border-primary bg-accent",
      )}
    >
      <div className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
        <Upload className="size-5" aria-hidden />
      </div>
      <div className="flex-1">
        <p className="font-semibold">Drop invoices or receipts here</p>
        <p className="text-sm text-muted-foreground">
          Digital PDFs, scans or phone photos. Each one is read, checked and filed in a few seconds.
        </p>
      </div>
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        multiple
        className="sr-only"
        aria-label="Choose files to upload"
        onChange={(e) => {
          if (e.target.files?.length) send(e.target.files);
          e.target.value = "";
        }}
      />
      <Button onClick={() => input.current?.click()} disabled={busy > 0}>
        {busy > 0 ? `Uploading ${busy}…` : "Choose files"}
      </Button>
    </div>
  );
}
