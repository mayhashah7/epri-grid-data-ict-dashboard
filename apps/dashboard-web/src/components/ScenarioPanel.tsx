import { useState, useEffect } from 'react';
import { postJson, API_BASE, type Substation } from '../lib/api';

interface ScenarioMeta {
  id: string;
  label: string;
  agent: string;
  hint: string;
}

export function ScenarioPanel({ onRan, substations }: { onRan: () => void; substations: Substation[] }) {
  const [scenarios, setScenarios] = useState<ScenarioMeta[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [last, setLast] = useState<string>('');
  const sub = substations[0]?.substation_id ?? '';

  useEffect(() => {
    fetch(API_BASE + '/api/scenarios')
      .then(r => r.json())
      .then(setScenarios)
      .catch(() => {});
  }, []);

  async function run(s: ScenarioMeta) {
    setBusy(s.id); setLast('');
    try {
      const body: any = s.id === 'storm-outage' ? { substation_id: sub, feeder_index: 7 }
                       : s.id === 'theft'       ? { substation_id: sub, count: 3 }
                       : s.id === 'heat-wave'   ? {}
                       : { substation_id: sub };
      const r = await postJson<any>(`/api/scenarios/${s.id}`, body);
      setLast(`✓ ${s.id} → ${r.agent_dispatched ?? 'dispatched'}`);
      onRan();
    } catch (e: any) { setLast(`error: ${e.message}`); }
    finally { setBusy(null); }
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-baseline justify-between mb-2">
        <h2 className="text-sm font-semibold tracking-wide">SCENARIOS</h2>
        <span className="text-xs text-slate-500">click to inject + auto-dispatch agent</span>
      </div>
      <div className="grid grid-cols-4 gap-1.5 flex-1 overflow-y-auto">
        {scenarios.map(s => (
          <button
            key={s.id}
            disabled={!!busy}
            onClick={() => run(s)}
            className="text-left p-1.5 rounded-lg bg-grid-bg border border-grid-border hover:border-grid-accent disabled:opacity-50 transition group"
            title={s.hint}
          >
            <div className="text-xs font-medium text-grid-accent leading-tight">{busy === s.id ? '⏳' : s.label}</div>
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

