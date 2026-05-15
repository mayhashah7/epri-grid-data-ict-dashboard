import { useState } from 'react';
import { postJson, type Substation } from '../lib/api';

const SCENARIOS = [
  { id: 'schematic-search', label: 'Schematic Q&A', agent: 'ict-schematic-knowledge-retrieval', hint: 'Find all 138kV breaker schemes installed since 2018' },
  { id: 'twin-drift', label: 'Digital Twin Drift', agent: 'ict-digital-twin-validation', hint: 'Live load on feeder F-12 diverges 9% from twin prediction' },
  { id: 'crew-update', label: 'Field Crew Update', agent: 'ict-gis-adms-sync', hint: 'Crew rerouted conductor on span 33-7 — sync model' },
  { id: 'threat-burst', label: 'OT Threat Burst', agent: 'ict-cyber-threat-hunting', hint: 'Spike in lateral SMB traffic between substations S-04 ↔ S-09' },
  { id: 'edge-anomaly', label: 'Edge Anomaly', agent: 'ict-edge-cyber-anomaly', hint: 'RTU R-118 reporting unsigned firmware update attempt' },
  { id: 'attack-prediction', label: 'Attack Path Prediction', agent: 'ict-predictive-attack-modeling', hint: 'Recon phase observed on HMI — predict next steps' },
  { id: 'kg-investigation', label: 'Knowledge Graph Pivot', agent: 'ict-knowledge-graph-asset', hint: 'Pivot from work-order WO-9821 to all related events' },
  { id: 'schematic-create', label: 'New Scheme Draft', agent: 'ict-schematic-creation', hint: 'Draft a one-line for a new 25kV recloser zone' },
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
            <div className="text-xs text-grid-info font-mono mt-0.5">→ {s.agent}</div>
            <div className="text-xs text-slate-500 mt-0.5 line-clamp-1">{s.hint}</div>
          </button>
        ))}
      </div>
      {last && <div className="text-xs text-grid-ok mt-1 truncate font-mono">{last}</div>}
    </div>
  );
}
