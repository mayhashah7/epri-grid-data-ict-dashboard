import { useState, useEffect, useRef } from 'react';
import { postJson, API_BASE, type Substation } from '../lib/api';
import type { ToastData } from './ScenarioToast';

interface ScenarioMeta {
  id: string;
  label: string;
  agent: string;
  hint: string;
}

interface Props {
  onRan: () => void;
  substations: Substation[];
  onToast?: (t: ToastData) => void;
}

export function ScenarioPanel({ onRan, substations, onToast }: Props) {
  const [scenarios, setScenarios] = useState<ScenarioMeta[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [last, setLast] = useState<string>('');
  const [demoRunning, setDemoRunning] = useState(false);
  const [demoIdx, setDemoIdx] = useState(-1);
  const stopRef = useRef(false);
  const sub = substations[0]?.substation_id ?? '';

  useEffect(() => {
    fetch(API_BASE + '/api/scenarios')
      .then(r => r.json())
      .then(setScenarios)
      .catch(() => {});
  }, []);

  async function run(s: ScenarioMeta, silent = false) {
    if (!silent) { setBusy(s.id); setLast(''); }
    onToast?.({ id: `${s.id}-${Date.now()}`, label: s.label, agent: s.agent, hint: s.hint });
    try {
      const body: Record<string, unknown> =
        s.id === 'storm-outage' ? { substation_id: sub, feeder_index: 7 }
        : s.id === 'theft'     ? { substation_id: sub, count: 3 }
        : s.id === 'heat-wave' ? {}
        : { substation_id: sub };
      const r = await postJson<any>(`/api/scenarios/${s.id}`, body);
      if (!silent) setLast(`✓ ${s.id} → ${r.agent_dispatched ?? 'dispatched'}`);
      onRan();
    } catch (e: any) {
      if (!silent) setLast(`error: ${e.message}`);
    } finally {
      if (!silent) setBusy(null);
    }
  }

  async function runDemo() {
    if (demoRunning) { stopRef.current = true; setDemoRunning(false); setDemoIdx(-1); return; }
    stopRef.current = false;
    setDemoRunning(true);
    for (let i = 0; i < scenarios.length; i++) {
      if (stopRef.current) break;
      setDemoIdx(i);
      await run(scenarios[i], true);
      // wait for agent activity to populate, then next scenario
      await new Promise(r => setTimeout(r, 4500));
    }
    setDemoRunning(false);
    setDemoIdx(-1);
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm font-semibold tracking-wide">SCENARIOS</h2>
        <div className="flex items-center gap-2">
          {demoRunning && demoIdx >= 0 && (
            <span className="text-xs text-grid-info font-mono animate-pulse">
              {demoIdx + 1}/{scenarios.length} — {scenarios[demoIdx]?.label ?? ''}
            </span>
          )}
          <button
            onClick={runDemo}
            className={`text-xs px-2.5 py-1 rounded border font-semibold transition ${
              demoRunning
                ? 'border-red-500 text-red-400 hover:bg-red-500/10'
                : 'border-grid-accent text-grid-accent hover:bg-grid-accent/10'
            }`}
          >
            {demoRunning ? '■ Stop Demo' : '▶ Run Full Demo'}
          </button>
        </div>
      </div>
      <div className="grid grid-cols-4 gap-1.5 flex-1 overflow-y-auto">
        {scenarios.map((s, i) => (
          <button
            key={s.id}
            disabled={!!busy}
            onClick={() => run(s)}
            className={`text-left p-1.5 rounded-lg border transition relative ${
              demoRunning && demoIdx === i
                ? 'border-grid-accent bg-grid-accent/15 shadow-[0_0_14px_rgba(251,191,36,0.3)]'
                : 'bg-grid-bg border-grid-border hover:border-grid-accent'
            } disabled:opacity-50`}
            title={s.hint}
          >
            {demoRunning && demoIdx === i && (
              <span className="absolute top-1 right-1 w-1.5 h-1.5 bg-grid-accent rounded-full animate-ping" />
            )}
            <div className="text-xs font-medium text-grid-accent leading-tight">
              {busy === s.id ? '⏳' : s.label}
            </div>
            <div className="text-xs text-grid-info font-mono mt-0.5">→ {s.agent}</div>
            <div className="text-xs text-slate-500 mt-0.5 line-clamp-1">{s.hint}</div>
          </button>
        ))}
        {scenarios.length === 0 && (
          <div className="col-span-4 text-xs text-slate-500 text-center py-4">Loading scenarios…</div>
        )}
      </div>
      {last && <div className="text-xs text-grid-ok mt-1 truncate font-mono">{last}</div>}
    </div>
  );
}
