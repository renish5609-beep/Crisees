"use client";

import { Layers } from "lucide-react";
import { useState } from "react";
import { DEFAULT_LAYERS, type LayerToggles } from "@/components/map/config";
import { RAMPS, THEMES, type ThemeId, themeById } from "@/lib/themes";

const LAYER_LABELS: { key: keyof LayerToggles; label: string; swatch: React.ReactNode }[] = [
  { key: "tracts", label: "Census tracts (theme)", swatch: <span className="h-3 w-3 rounded-sm bg-[#7a5f8f]" /> },
  { key: "floodZones", label: "FEMA flood zones", swatch: <span className="h-3 w-3 rounded-sm bg-[#4fb3e8]" /> },
  { key: "coverage", label: "FEMA data coverage / no data", swatch: <span className="h-3 w-3 rounded-sm hatch-sw" /> },
  { key: "closures", label: "Simulated road closures", swatch: <span className="h-0.5 w-3 bg-[#ff4d5e]" /> },
  { key: "selectedHubs", label: "Optimiser-selected hubs", swatch: <span className="h-3 w-3 rounded-full bg-[#7ee0b5]" /> },
  { key: "allocations", label: "Hub → shelter allocations", swatch: <span className="h-0 w-3 border-t-2 border-dashed border-[#e8e2cf]" /> },
  { key: "shelters", label: "Assumed shelters", swatch: <span className="h-3 w-3 border-2 border-[#e8e2cf]" /> },
  { key: "candidateHubs", label: "Candidate hubs (249)", swatch: <span className="h-2.5 w-2.5 rounded-full border border-[#9fb3c0]" /> },
  { key: "roads", label: "Major roads", swatch: <span className="h-0.5 w-3 bg-[#7f909d]" /> },
  { key: "basemap", label: "Basemap tiles", swatch: <span className="h-3 w-3 rounded-sm bg-[#1e2a33]" /> },
];

export function ThemePicker({ value, onChange }: { value: ThemeId; onChange: (t: ThemeId) => void }) {
  const groups = [...new Set(THEMES.map((t) => t.group))];
  return (
    <label className="flex items-center gap-2 rounded-md border border-rule bg-panel/90 px-2 py-1.5 text-sm backdrop-blur">
      <span className="sr-only">Map theme</span>
      <select value={value} onChange={(e) => onChange(e.target.value as ThemeId)}
        className="max-w-60 bg-transparent text-ink focus:outline-none" aria-label="Colour tracts by">
        {groups.map((g) => (
          <optgroup key={g} label={g}>
            {THEMES.filter((t) => t.group === g).map((t) => <option key={t.id} value={t.id} className="bg-panel">{t.label}</option>)}
          </optgroup>
        ))}
      </select>
    </label>
  );
}

export function LayerMenu({ layers, onChange }: { layers: LayerToggles; onChange: (l: LayerToggles) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-controls="layer-menu"
        className="flex items-center gap-2 rounded-md border border-rule bg-panel/90 px-2.5 py-1.5 text-sm text-ink backdrop-blur hover:border-water/60">
        <Layers size={15} aria-hidden /> Layers
      </button>
      {open && (
        <div id="layer-menu" className="crisees-in absolute right-0 z-20 mt-1 w-64 rounded-lg border border-rule bg-panel/95 p-2 shadow-xl backdrop-blur">
          {LAYER_LABELS.filter(({ key }) => key !== "basemap" || DEFAULT_LAYERS.basemap).map(({ key, label, swatch }) => (
            <label key={key} className="flex cursor-pointer items-center gap-2.5 rounded px-2 py-1.5 text-sm hover:bg-raised">
              <input type="checkbox" checked={layers[key]} onChange={(e) => onChange({ ...layers, [key]: e.target.checked })}
                className="accent-[#63b4d6]" />
              <span className="grid w-4 place-items-center">{swatch}</span>
              <span className="text-ink/90">{label}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

export function Legend({ theme, domain }: { theme: ThemeId; domain: [number, number] | null }) {
  const t = themeById(theme);
  const colors = RAMPS[t.ramp];
  const [open, setOpen] = useState(false);
  return (
    <div className="w-64 space-y-2 rounded-lg border border-rule bg-panel/90 p-3 text-xs backdrop-blur" aria-label="Map legend">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="flex w-full items-center justify-between text-left font-medium text-ink">
        {t.label}<span className="text-muted">{open ? "Less" : "Key"}</span>
      </button>
      <div className="h-2 rounded-full" style={{ background: `linear-gradient(90deg, ${colors.join(",")})` }} />
      {domain && (
        <div className="flex justify-between tabular-nums text-muted">
          <span>{t.format(domain[0])}</span><span>{t.format(domain[1])}+</span>
        </div>
      )}
      {open && <div className="crisees-in space-y-2">
      <p className="flex items-center gap-2 text-muted"><span className="h-3 w-4 rounded-sm hatch-gray" /> Unknown / unavailable (not zero)</p>
      <p className="flex items-center gap-2 text-muted"><span className="h-3 w-4 rounded-sm hatch-sw" /> No FEMA data: flood hazard unknown</p>
      <p className="flex items-center gap-2 text-muted"><span className="h-3 w-4 rounded-sm bg-[#4fb3e8]/70" /> FEMA 1% annual-chance zone (regulatory)</p>
      <p className="flex items-center gap-2 text-muted"><span className="h-0.5 w-4 bg-[#ff4d5e]" /> Hypothetical road closure</p>
      <p className="flex items-center gap-2 text-muted"><span className="h-0 w-4 border-t-2 border-dashed border-[#e8e2cf]" /> Conceptual allocation (not a route)</p>
      <p className="leading-snug text-muted/80">{t.description}</p>
      </div>}
    </div>
  );
}
