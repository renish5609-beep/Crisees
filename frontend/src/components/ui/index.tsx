"use client";

import { AlertTriangle, CheckCircle2, Info, Loader2, RotateCcw } from "lucide-react";
import { useEffect, useId, useState } from "react";
import type { ApiError } from "@/lib/api";

export function Button({
  children, onClick, variant = "primary", disabled, type = "button", className = "", ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" }) {
  const styles = {
    primary: "bg-water text-ground hover:bg-[#7fc4e1] disabled:bg-raised disabled:text-muted",
    secondary: "border border-rule bg-raised text-ink hover:border-water/60 disabled:text-muted",
    ghost: "text-muted hover:bg-raised hover:text-ink disabled:opacity-50",
  }[variant];
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      className={`inline-flex items-center justify-center gap-2 rounded-md px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed ${styles} ${className}`}
      {...rest}>
      {children}
    </button>
  );
}

export function Slider({
  label, value, onChange, min, max, step, unit, hint, format,
}: {
  label: string; value: number; onChange: (v: number) => void; min: number; max: number; step: number;
  unit?: string; hint?: string; format?: (v: number) => string;
}) {
  const id = useId();
  const [text, setText] = useState(String(value));
  useEffect(() => setText(String(value)), [value]);
  const commit = (raw: string) => {
    const v = Number(raw);
    if (Number.isFinite(v)) onChange(Math.min(max, Math.max(min, v)));
    else setText(String(value));
  };
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={id} className="text-sm text-ink/90">{label}</label>
        <span className="flex items-baseline gap-1 text-sm">
          <input aria-label={`${label} value`} value={text} inputMode="decimal"
            onChange={(e) => setText(e.target.value)} onBlur={(e) => commit(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && commit((e.target as HTMLInputElement).value)}
            className="w-16 rounded border border-transparent bg-transparent text-right font-medium tabular-nums text-ink hover:border-rule focus:border-water focus:outline-none" />
          {unit && <span className="text-xs text-muted">{unit}</span>}
        </span>
      </div>
      <input id={id} type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-valuetext={format ? format(value) : `${value}${unit ? ` ${unit}` : ""}`}
        className="crisees-range w-full" />
      {hint && <p className="text-xs leading-relaxed text-muted">{hint}</p>}
    </div>
  );
}

export function Segmented<T extends string>({
  options, value, onChange, label,
}: { options: { value: T; label: string; hint?: string }[]; value: T; onChange: (v: T) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="grid auto-cols-fr grid-flow-col gap-1 rounded-lg border border-rule bg-ground/60 p-1">
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={value === o.value} title={o.hint}
          onClick={() => onChange(o.value)}
          className={`rounded-md px-2 py-1.5 text-sm transition-colors ${value === o.value ? "bg-raised text-ink shadow-sm" : "text-muted hover:text-ink"}`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Stat({ label, value, sub, tone = "default" }: {
  label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: "default" | "good" | "warn" | "bad";
}) {
  const color = { default: "text-ink", good: "text-[#7ee0b5]", warn: "text-sediment", bad: "text-alarm" }[tone];
  return (
    <div className="min-w-0 rounded-lg border border-rule bg-ground/40 p-3">
      <p className="text-xs text-muted">{label}</p>
      <p className={`mt-1 text-xl font-semibold tabular-nums tracking-tight ${color}`}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-muted">{sub}</p>}
    </div>
  );
}

export function Badge({ children, tone = "default", title }: { children: React.ReactNode; tone?: "default" | "good" | "warn" | "bad" | "info"; title?: string }) {
  const styles = {
    default: "border-rule text-muted",
    good: "border-[#7ee0b5]/40 text-[#7ee0b5]",
    warn: "border-sediment/50 text-sediment",
    bad: "border-alarm/50 text-alarm",
    info: "border-water/40 text-water",
  }[tone];
  return <span title={title} className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs ${styles}`}>{children}</span>;
}

export function ErrorCard({ error, what, onRetry }: { error: ApiError; what: string; onRetry?: () => void }) {
  const hint = typeof error.details.hint === "string" ? error.details.hint : null;
  return (
    <div role="alert" className="rounded-lg border border-alarm/40 bg-alarm/5 p-3 text-sm">
      <p className="flex items-center gap-2 font-medium text-alarm"><AlertTriangle size={15} aria-hidden /> {what} failed</p>
      <p className="mt-1 text-ink/90">{error.message}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
      {Array.isArray(error.details.issues) && <p className="mt-1 text-xs text-muted">{(error.details.issues as string[]).join("; ")}</p>}
      {onRetry && (
        <Button variant="secondary" className="mt-2" onClick={onRetry}><RotateCcw size={14} aria-hidden /> Retry</Button>
      )}
    </div>
  );
}

export function Working({ label, startedAt }: { label: string; startedAt?: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, []);
  const secs = startedAt ? ((now - startedAt) / 1000).toFixed(1) : null;
  return (
    <p role="status" className="flex items-center gap-2 text-sm text-water">
      <Loader2 size={15} className="animate-spin" aria-hidden /> {label}
      {secs && <span className="tabular-nums text-muted">{secs}s</span>}
    </p>
  );
}

export function Note({ children, tone = "info" }: { children: React.ReactNode; tone?: "info" | "warn" | "ok" }) {
  const Icon = tone === "warn" ? AlertTriangle : tone === "ok" ? CheckCircle2 : Info;
  const color = tone === "warn" ? "text-sediment" : tone === "ok" ? "text-[#7ee0b5]" : "text-water";
  return (
    <p className="flex gap-2 text-xs leading-relaxed text-muted">
      <Icon size={14} className={`mt-0.5 shrink-0 ${color}`} aria-hidden />
      <span>{children}</span>
    </p>
  );
}

export function Section({ title, children, aside }: { title: string; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-2 border-b border-rule pb-1.5">
        <h3 className="text-sm font-medium text-ink/90">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function Meter({ value, label, tone = "info" }: { value: number | null; label: string; tone?: "info" | "warn" }) {
  const v = value == null ? 0 : Math.max(0, Math.min(1, value));
  return (
    <div>
      <div className="flex justify-between text-xs"><span className="text-muted">{label}</span>
        <span className="tabular-nums text-ink">{value == null ? "n/a" : `${(value * 100).toFixed(0)}%`}</span></div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-raised" role="meter" aria-label={label}
        aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(v * 100)}>
        <div className={`h-full rounded-full ${tone === "warn" ? "bg-sediment" : "bg-water"}`} style={{ width: `${v * 100}%` }} />
      </div>
    </div>
  );
}

export const fmt = {
  int: (v: number | null | undefined) => (v == null ? "Unknown" : Math.round(v).toLocaleString("en-US")),
  dec: (v: number | null | undefined, d = 1) => (v == null ? "Unknown" : v.toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d })),
  pct: (v: number | null | undefined, d = 1) => (v == null ? "Unknown" : `${(v * 100).toFixed(d)}%`),
  pctRaw: (v: number | null | undefined, d = 1) => (v == null ? "Unknown" : `${v.toFixed(d)}%`),
  signed: (v: number | null | undefined, d = 0) => (v == null ? "Unknown" : `${v > 0 ? "+" : ""}${v.toLocaleString("en-US", { maximumFractionDigits: d })}`),
};

export const CASE_LABELS: Record<string, string> = {
  baseline_no_intervention: "Baseline, no intervention",
  disrupted_no_intervention: "Flood, no intervention",
  disrupted_equity_optimized: "Flood + equity-weighted plan",
  disrupted_equal_weight_optimized: "Flood + equal-weight plan",
  baseline_plan_under_disruption: "Baseline hubs reused in flood",
};

export const STATUS_TEXT: Record<string, { label: string; tone: "good" | "warn" | "bad" }> = {
  optimal: { label: "Proven optimal", tone: "good" },
  optimal_within_gap: { label: "Optimal within gap", tone: "good" },
  time_limit_feasible: { label: "Time limit: feasible, not proven optimal", tone: "warn" },
};
