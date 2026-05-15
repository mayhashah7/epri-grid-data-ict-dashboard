import { useState } from 'react';
import { postJson, type Substation } from '../lib/api';

const SCENARIOS = [
  { id: 'storm-outage',     label: '⛈️ Storm Outage',         agent: 'outage-detection',       hint: 'Knocks a feeder offline' },
  { id: 'theft',            label: '🕵️ Theft Pattern',        agent: 'theft-detection',        hint: 'Plant tampers + flat reads' },
  { id: 'der-overvoltage',  label: '☀️ Solar Backfeed',       agent: 'der-management',         hint: 'Volt-VAR risk on secondaries' },
  { id: 'heat-wave',        label: '🔥 Heat Wave',            agent: 'demand-response',        hint: 'Trigger DR cohort selection' },
  { id: 'transformer-aging',label: '🔧 Transformer Aging',    agent: 'predictive-maintenance', hint: 'Score asset health' },
  { id: 'cyber-burst',      label: '🛡️ Cyber Anomaly',        agent: 'grid-cybersecurity',     hint: 'Unauthorized firmware queries' },
  { id: 'ev-surge',         label: '🔌 EV Plug-in Surge',     agent: 'ev-load-orchestration',  hint: 'Evening EV charging burst' },
  { id: 'weather-alert',    label: '🌦️ Weather Alert',         agent: 'weather-impact',         hint: 'Heat warning + storm watch' },
];

export function ScenarioPanel({ onRan, substations }: { onRan: () => void; substations: Substation[] }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [last, setLast] = useState<string>('');
  const sub = substations[0]?.substation_id ?? '';

  async function run(id: string) {
    setBusy(id); setLast('');
    try {
      const body: any = id === 'storm-outage' ? { substation_id: sub, feeder_index: 7 }
                       : id === 'theft'       ? { substation_id: sub, count: 3 }
                       : id === 'heat-wave'   ? {}
                       : { substation_id: sub };
      const r = await postJson<any>(`/api/scenarios/${id}`, body);
      setLast(`✓ ${id} → ${r.agent_dispatched ?? 'dispatched'}`);
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
        {SCENARIOS.map(s => (
          <button
            key={s.id}
            disabled={!!busy}
            onClick={() => run(s.id)}
            className="text-left p-1.5 rounded-lg bg-grid-bg border border-grid-border hover:border-grid-accent disabled:opacity-50 transition group"
            title={s.hint}
          >
            <div className="text-xs font-medium text-grid-accent leading-tight">{busy === s.id ? '⏳' : s.label}</div>
            <div className="text-xs text-grid-info font-mono mt-0.5">→ ami-{s.agent}</div>
            <div className="text-xs text-slate-500 mt-0.5 line-clamp-1">{s.hint}</div>
          </button>
        ))}
      </div>
      {last && <div className="text-xs text-grid-ok mt-1 truncate font-mono">{last}</div>}
    </div>
  );
}
