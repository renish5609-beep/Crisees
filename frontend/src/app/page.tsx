"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";
import { DEFAULT_LAYERS, type EdgeFeature, type LayerToggles, tractValue } from "@/components/map/config";
import { Legend, LayerMenu, ThemePicker } from "@/components/panels/MapControls";
import { Overview } from "@/components/panels/Overview";
import { ScenarioLab } from "@/components/panels/ScenarioLab";
import { TractInspector } from "@/components/panels/TractInspector";
import { useWorkspace } from "@/lib/store";
import { type ThemeId, themeById } from "@/lib/themes";

const CriseesMap = dynamic(() => import("@/components/map/CriseesMap"), {
  ssr: false,
  loading: () => <div className="absolute inset-0 grid place-items-center text-sm text-muted">Loading map…</div>,
});

const PanelLoading = () => <p className="text-sm text-muted">Loading panel…</p>;
const AccessibilityPanel = dynamic(() => import("@/components/panels/Accessibility").then((m) => m.AccessibilityPanel), { loading: PanelLoading });
const Planner = dynamic(() => import("@/components/panels/Planner").then((m) => m.Planner), { loading: PanelLoading });
const ImpactPanel = dynamic(() => import("@/components/panels/Impact").then((m) => m.ImpactPanel), { loading: PanelLoading });
const GuidedDemo = dynamic(() => import("@/components/panels/GuidedDemo").then((m) => m.GuidedDemo), { loading: PanelLoading });

const VIEW_THEME: Partial<Record<string, ThemeId>> = {
  access: "newly_no_drive_route_share",
  planner: "plan_coverage",
};

export default function Workspace() {
  const ws = useWorkspace();
  const [theme, setTheme] = useState<ThemeId>("demand_est");
  const [layers, setLayers] = useState<LayerToggles>(DEFAULT_LAYERS);
  const [picking, setPicking] = useState(false);
  const [picked, setPicked] = useState<EdgeFeature[]>([]);
  const [demoStep, setDemoStep] = useState(0);
  const [focus, setFocus] = useState<{ bbox: [number, number, number, number]; n: number } | null>(null);
  const frame = useCallback((bbox: [number, number, number, number] | null) => {
    if (bbox) setFocus((f) => ({ bbox, n: (f?.n ?? 0) + 1 }));
  }, []);

  // Entering the guided demo always starts from step 1 with a clean selection.
  useEffect(() => {
    if (ws.view !== "demo") return;
    setDemoStep(0);
    ws.selectHub(null);
    ws.selectTract(null);
  }, [ws.view]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const t = VIEW_THEME[ws.view];
    if (t && (t !== "plan_coverage" || ws.plan.data)) setTheme(t);
    if (ws.view !== "scenario") setPicking(false);
  }, [ws.view, ws.plan.data]);

  const onPickEdge = useCallback((f: EdgeFeature) => {
    const id = f.properties.edge_id;
    setPicked((prev) => (prev.some((p) => p.properties.edge_id === id) ? prev : [...prev, f]));
    ws.setParams((p) => {
      if (!p.scenario.custom_closed_edge_ids.includes(id)) p.scenario.custom_closed_edge_ids.push(id);
      return p;
    });
  }, [ws]);
  const removePicked = useCallback((id: string) => {
    setPicked((prev) => prev.filter((p) => p.properties.edge_id !== id));
    ws.setParams((p) => ({ ...p, scenario: { ...p.scenario, custom_closed_edge_ids: p.scenario.custom_closed_edge_ids.filter((e) => e !== id) } }));
  }, [ws]);

  const domain = useMemo<[number, number] | null>(() => {
    const t = themeById(theme);
    if (t.domain !== "data") return t.domain;
    const vals = (ws.scenario.data?.accessibility.features ?? []).map((f) => tractValue(theme, f.properties)).filter((v): v is number => v != null);
    return vals.length ? [0, Math.max(...vals)] : null;
  }, [theme, ws.scenario.data]);

  const startDemo = () => ws.setView("demo");

  return (
    <div className="flex h-full flex-col lg:flex-row">
      <section aria-label="Map" className="relative h-[58dvh] min-h-80 shrink-0 lg:h-auto lg:min-h-0 lg:flex-1">
        <CriseesMap
          bundle={ws.scenario.data}
          plan={ws.plan.data}
          demographics={ws.demographics}
          theme={theme}
          layers={layers}
          selectedTract={ws.selectedTract}
          onSelectTract={ws.selectTract}
          selectedHub={ws.selectedHub}
          onSelectHub={(h) => { ws.selectHub(h); if (h && ws.view !== "demo") ws.setView("planner"); }}
          pickRoads={picking}
          onPickEdge={onPickEdge}
          customClosureFeatures={picked}
          focus={focus}
        />
        <div className="pointer-events-none absolute inset-x-3 top-3 flex flex-wrap items-start justify-between gap-2">
          <div className="pointer-events-auto"><ThemePicker value={theme} onChange={setTheme} /></div>
          <div className="pointer-events-auto"><LayerMenu layers={layers} onChange={setLayers} /></div>
        </div>
        <div className="absolute bottom-8 left-3 hidden sm:block"><Legend theme={theme} domain={domain} /></div>
        {picking && (
          <div className="absolute inset-x-0 bottom-3 mx-auto w-fit rounded-full border border-[#ffd166]/60 bg-panel/95 px-4 py-1.5 text-sm text-[#ffd166]">
            Click a road to add a custom closure
          </div>
        )}
      </section>
      <aside aria-label="Analysis panel" className="min-h-0 overflow-y-auto border-rule bg-panel/40 p-5 lg:w-[30rem] lg:border-l">
        <div className="space-y-5">
          {ws.view !== "demo" && <TractInspector />}
          {ws.view === "overview" && <Overview startDemo={startDemo} />}
          {ws.view === "scenario" && <ScenarioLab picking={picking} setPicking={setPicking} picked={picked} onRemovePicked={removePicked} />}
          {ws.view === "access" && <AccessibilityPanel setTheme={setTheme} />}
          {ws.view === "planner" && <Planner />}
          {ws.view === "impact" && <ImpactPanel />}
          {ws.view === "demo" && (
            <GuidedDemo step={demoStep} setStep={setDemoStep} exit={() => ws.setView("overview")} ctx={{ setTheme, setLayers, frame }} />
          )}
        </div>
      </aside>
    </div>
  );
}
