import type { Metadata } from "next";

import { ResultsView } from "@/components/results-view";

export const metadata: Metadata = { title: "Test results" };

export default function Page() {
  return <ResultsView />;
}
