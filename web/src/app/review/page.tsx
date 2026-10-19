import type { Metadata } from "next";

import { ReviewQueue } from "@/components/review-queue";

export const metadata: Metadata = { title: "Review queue" };

export default function Page() {
  return <ReviewQueue />;
}
