import { Suspense } from "react";

import { DocumentView } from "@/components/document-view";
import { Skeleton } from "@/components/ui/skeleton";

export default function Page() {
  return (
    <Suspense fallback={<div className="mx-auto max-w-6xl space-y-4 px-4 py-8 sm:px-8"><Skeleton className="h-8 w-72" /><Skeleton className="h-[60vh] w-full" /></div>}>
      <DocumentView />
    </Suspense>
  );
}
