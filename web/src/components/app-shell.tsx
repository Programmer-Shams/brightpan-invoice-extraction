"use client";

import Link from "next/link";
import { Suspense } from "react";
import { usePathname } from "next/navigation";
import useSWR from "swr";
import { ClipboardCheck, FileStack, Gauge } from "lucide-react";

import { fetcher, type DocumentSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Documents", icon: FileStack, match: (p: string) => p === "/" || p.startsWith("/documents") },
  { href: "/review", label: "Review queue", icon: ClipboardCheck, match: (p: string) => p.startsWith("/review") },
  { href: "/results", label: "Test results", icon: Gauge, match: (p: string) => p.startsWith("/results") },
];

function PanMark() {
  // A skillet seen from above: the store's mark, drawn in enamel blue.
  return (
    <svg viewBox="0 0 32 32" aria-hidden className="size-7 shrink-0">
      <circle cx="13" cy="16" r="10" fill="var(--primary)" />
      <circle cx="13" cy="16" r="6.5" fill="none" stroke="#fff" strokeOpacity=".35" strokeWidth="1.5" />
      <rect x="22" y="14" width="9" height="4" rx="2" fill="var(--foreground)" />
    </svg>
  );
}

function NavLinks({ pathname }: { pathname: string | null }) {
  const { data: open } = useSWR<DocumentSummary[]>("/api/review?status=open", fetcher, { refreshInterval: 5000 });
  return (
    <nav aria-label="Main" className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:pb-0">
      {NAV.map(({ href, label, icon: Icon, match }) => {
        const active = pathname !== null && match(pathname);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex shrink-0 items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground",
              active && "bg-card text-foreground shadow-[inset_3px_0_0_var(--primary)]",
            )}
          >
            <Icon className="size-4" aria-hidden />
            <span>{label}</span>
            {href === "/review" && open && open.length > 0 && (
              <span className="ml-auto rounded-full bg-review px-1.5 text-[11px] font-semibold leading-5 text-white tabular-nums">
                {open.length}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}

// The current URL is only known at request time, so the active state streams in under Suspense.
function ActiveNav() {
  return <NavLinks pathname={usePathname()} />;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="border-b border-border bg-rail md:sticky md:top-0 md:h-screen md:w-60 md:shrink-0 md:border-r md:border-b-0">
        <div className="flex items-center gap-2.5 px-5 pt-5 pb-4 md:pb-8">
          <PanMark />
          <div className="leading-tight">
            <div className="text-[15px] font-bold tracking-tight">Brightpan</div>
            <div className="text-xs text-muted-foreground">Accounts payable</div>
          </div>
        </div>
        <Suspense fallback={<NavLinks pathname={null} />}>
          <ActiveNav />
        </Suspense>
      </aside>
      <main className="min-w-0 flex-1">{children}</main>
    </div>
  );
}
