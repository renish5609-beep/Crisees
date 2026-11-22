"use client";

import { BookOpen, FlaskConical, Footprints, LayoutDashboard, Play, Scale, Truck } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type View, useWorkspace } from "@/lib/store";

const VIEWS: { view: View; label: string; Icon: typeof LayoutDashboard }[] = [
  { view: "overview", label: "Overview", Icon: LayoutDashboard },
  { view: "scenario", label: "Scenario Lab", Icon: FlaskConical },
  { view: "access", label: "Accessibility", Icon: Footprints },
  { view: "planner", label: "Intervention Planner", Icon: Truck },
  { view: "impact", label: "Impact Analysis", Icon: Scale },
];

export function Rail() {
  const ws = useWorkspace();
  const path = usePathname();
  const router = useRouter();
  const onWorkspace = path === "/";
  const go = (v: View) => {
    ws.setView(v);
    if (!onWorkspace) router.push(`/?view=${v}`);
  };
  const item = (active: boolean) =>
    `flex shrink-0 items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors ${active ? "bg-raised text-ink" : "text-muted hover:bg-raised/60 hover:text-ink"}`;
  return (
    <nav aria-label="Primary" className="flex items-center gap-1 overflow-x-auto border-b border-rule bg-panel px-3 py-2 lg:h-dvh lg:flex-col lg:items-stretch lg:gap-1 lg:overflow-visible lg:border-r lg:border-b-0 lg:px-3 lg:py-4">
      <Link href="/" onClick={() => ws.setView("overview")} className="mr-2 flex shrink-0 items-center gap-2.5 px-2 lg:mb-4 lg:mr-0">
        <Mark />
        <span className="text-[17px] font-semibold tracking-tight">Crisees</span>
      </Link>
      {VIEWS.map(({ view, label, Icon }) => (
        <button key={view} onClick={() => go(view)} aria-current={onWorkspace && ws.view === view ? "page" : undefined}
          className={item(onWorkspace && ws.view === view)}>
          <Icon size={16} aria-hidden /> <span>{label}</span>
        </button>
      ))}
      <Link href="/methodology" aria-current={path.startsWith("/methodology") ? "page" : undefined} className={item(path.startsWith("/methodology"))}>
        <BookOpen size={16} aria-hidden /> <span>Data &amp; Methodology</span>
      </Link>
      <button onClick={() => go("demo")} aria-current={onWorkspace && ws.view === "demo" ? "page" : undefined}
        className="ml-1 flex shrink-0 items-center gap-2 rounded-md border border-water/40 px-3 py-2 text-sm text-water hover:bg-water/10 lg:mt-3 lg:ml-0">
        <Play size={15} aria-hidden /> Run guided demo
      </button>
      <p className="mt-auto hidden px-2 text-xs leading-relaxed text-muted lg:block">
        Research and planning prototype. Not an emergency warning, evacuation order, shelter directory or dispatch service.
      </p>
    </nav>
  );
}

function Mark() {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
      <path d="M2 16c3-2 6-2 9 0s6 2 9 0" fill="none" stroke="var(--color-water)" strokeWidth="1.8" />
      <path d="M5 11.5c2-3 10-3 12 0" fill="none" stroke="var(--color-ink)" strokeWidth="1.4" opacity=".75" />
      <circle cx="11" cy="6.5" r="2" fill="#7ee0b5" />
    </svg>
  );
}
