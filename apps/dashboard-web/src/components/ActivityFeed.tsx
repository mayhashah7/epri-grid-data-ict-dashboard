type Activity = { id: string; agent?: string; tool?: string; text?: string; ts: number };

// Map agent names to their brand colors
const AGENT_COLORS: Record<string, string> = {
  'ami-orchestrator': '#fbbf24',
  'ami-outage-detection': '#ef4444',
  'ami-theft-detection': '#f97316',
  'ami-der-management': '#facc15',
  'ami-demand-response': '#a855f7',
  'ami-predictive-maintenance': '#0ea5e9',
  'ami-billing-anomaly': '#10b981',
  'ami-customer-service': '#94a3b8',
  'ami-grid-cybersecurity': '#dc2626',
  'ami-ev-load-orchestration': '#22d3ee',
  'ami-weather-impact': '#60a5fa',
  'ami-tariff-optimization': '#34d399',
};

function agentColor(name?: string) {
  if (!name) return '#94a3b8';
  const exact = AGENT_COLORS[name];
  if (exact) return exact;
  // EPRI: match by suffix
  const entry = Object.entries(AGENT_COLORS).find(([k]) => name.endsWith(k.split('-').slice(1).join('-')));
  return entry?.[1] ?? '#38bdf8';
}

export function ActivityFeed({ items, onClear }: { items: Activity[]; onClear?: () => void }) {
  const reversed = [...items].reverse();
  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm font-semibold tracking-wide">LIVE AGENT ACTIVITY</h2>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">{items.length} events</span>
          {onClear && items.length > 0 && (
            <button
              onClick={onClear}
              className="text-xs text-slate-500 hover:text-slate-300 border border-grid-border px-1.5 py-0.5 rounded"
            >clear</button>
          )}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto scroll-fade text-xs font-mono space-y-0.5 pr-1">
        {items.length === 0 && (
          <div className="text-slate-500 text-xs">Waiting for agent activity… fire a scenario or ask in chat.</div>
        )}
        {reversed.map((it, idx) => (
          <div
            key={it.id}
            className={`flex items-baseline gap-1.5 border-b border-grid-border/30 pb-0.5 ${idx === 0 ? 'animate-fadeIn' : ''}`}
          >
            <span className="text-slate-500 w-12 shrink-0 tabular-nums">
              {new Date(it.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
            {/* colored agent dot */}
            <span
              className="w-1.5 h-1.5 rounded-full shrink-0 self-center"
              style={{ backgroundColor: agentColor(it.agent) }}
            />
            {it.tool ? (
              <>
                <span className="text-grid-info">→</span>
                <span className="text-grid-accent font-semibold">{it.tool}</span>
                {it.text && <span className="text-slate-500 truncate">{it.text}</span>}
              </>
            ) : (
              <span className="text-emerald-300 truncate">{it.text}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
