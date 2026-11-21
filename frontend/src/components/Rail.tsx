"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "Workspace", hint: "Study area map" },
  { href: "/data", label: "Data status", hint: "Datasets and sources" },
];

const LATER = ["Accessibility analysis", "Pickup hub planning", "Scenarios"];

export function Rail() {
  const path = usePathname();
  return (
    <nav
      aria-label="Primary"
      className="flex flex-row items-center gap-6 border-b border-rule bg-panel px-4 py-3 md:flex-col md:items-stretch md:gap-8 md:border-r md:border-b-0 md:px-4 md:py-5"
    >
      <Link href="/" className="flex items-center gap-2.5">
        <Mark />
        <span className="text-[17px] font-semibold tracking-tight">Crisees</span>
      </Link>
      <ul className="flex gap-1 md:flex-col">
        {NAV.map((item) => {
          const active = item.href === "/" ? path === "/" : path.startsWith(item.href);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`block rounded-md px-3 py-2 text-sm ${
                  active ? "bg-raised text-ink" : "text-muted hover:bg-raised/60 hover:text-ink"
                }`}
              >
                <span className="block font-medium">{item.label}</span>
                <span className="hidden text-xs text-muted md:block">{item.hint}</span>
              </Link>
            </li>
          );
        })}
      </ul>
      <div className="hidden md:block">
        <p className="px-3 text-xs text-muted">Coming in later phases</p>
        <ul className="mt-2 space-y-1">
          {LATER.map((l) => (
            <li key={l} className="px-3 py-1 text-sm text-muted/60">
              {l}
            </li>
          ))}
        </ul>
      </div>
      <p className="mt-auto hidden px-3 text-xs leading-relaxed text-muted md:block">
        Planning and simulation only. Not an emergency dispatch system.
      </p>
    </nav>
  );
}

function Mark() {
  // Three contour lines rising out of a waterline: elevation versus flood.
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
      <path d="M2 16c3-2 6-2 9 0s6 2 9 0" fill="none" stroke="var(--color-water)" strokeWidth="1.8" />
      <path d="M5 11.5c2-3 10-3 12 0" fill="none" stroke="var(--color-ink)" strokeWidth="1.4" opacity=".75" />
      <path d="M8 7c1.5-2 4.5-2 6 0" fill="none" stroke="var(--color-ink)" strokeWidth="1.4" opacity=".45" />
    </svg>
  );
}
