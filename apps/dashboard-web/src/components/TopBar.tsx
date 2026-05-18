interface WsStatus { connected: boolean; reconnecting: boolean; }

type Props = {
  systemKw: number;
  substations: number;
  foundry: boolean;
  agentCount: number;
  activeCases?: number;
  resolvedCases?: number;
  onlineMetricsPct?: number;
  wsStatus?: WsStatus;
  onReset?: () => void;
};

export function TopBar({
  systemKw, substations, foundry, agentCount,
  activeCases, resolvedCases, onlineMetricsPct,
  wsStatus, onReset,
}: Props) {
  const mw = (systemKw / 1000).toFixed(1);
  const wsColor = !wsStatus
    ? 'text-slate-500'
    : wsStatus.reconnecting ? 'text-yellow-400 animate-pulse'
    : wsStatus.connected    ? 'text-emerald-400'
    : 'text-red-400';
  const wsLabel = !wsStatus ? '● —'
    : wsStatus.reconnecting ? '● reconn…'
    : wsStatus.connected    ? '● live'
    : '● offline';

  return (
    <header className="px-4 py-2.5 border-b border-grid-border bg-grid-panel flex items-center gap-4 shrink-0">
      <div className="flex items-center gap-2">
        <span className="text-grid-accent text-2xl">📡</span>
        <div>
          <h1 className="text-base font-bold tracking-wide leading-none">Grid Data & ICT Agentic Dashboard</h1>
          <div className="text-xs text-slate-500 mt-0.5">Power & Utilities · {agentCount}-Agent Foundry Fabric</div>
        </div>
      </div>
      <div className="ml-auto flex items-center gap-5 text-xs font-mono">
        <Stat label="System Load" value={${"$"}{mw} MW} accent />
        <Stat label="Substations" value={substations.toString()} />
        {onlineMetricsPct != null && (
          <Stat label="Meters Online" value={${"$"}{onlineMetricsPct.toFixed(1)}%}
            accent={onlineMetricsPct > 97} warn={onlineMetricsPct < 95} />
        )}
        {activeCases != null && (
          <Stat label="Active Cases" value={activeCases.toString()} warn={activeCases > 0} />
        )}
        {resolvedCases != null && (
          <Stat label="Resolved" value={resolvedCases.toString()} ok />
        )}
        <Stat label="Agents" value={agentCount.toString()} accent />
        <Stat label="Foundry" value={foundry ? 'live' : 'mock'} accent={foundry} dim={!foundry} />
        <div className="flex flex-col items-end leading-tight">
          <span className="text-xs uppercase tracking-widest text-slate-500">Stream</span>
          <span className={	ext-sm font-semibold {wsColor}}>{wsLabel}</span>
        </div>
        {onReset && (
          <button onClick={onReset}
            className="text-xs px-2.5 py-1 border border-grid-border rounded hover:border-red-500 hover:text-red-400 text-slate-400 transition"
            title="Reset all cases, events and meters for a fresh demo">
            ⟳ Reset Demo
          </button>
        )}
      </div>
    </header>
  );
}

function Stat({ label, value, accent, dim, warn, ok }: {
  label: string; value: string; accent?: boolean; dim?: boolean; warn?: boolean; ok?: boolean;
}) {
  const color = ok ? 'text-emerald-400' : warn ? 'text-amber-400' : accent ? 'text-grid-accent' : dim ? 'text-slate-500' : 'text-white';
  return (
    <div className="flex flex-col items-end leading-tight">
      <span className="text-xs uppercase tracking-widest text-slate-500">{label}</span>
      <span className={	ext-sm font-semibold {color}}>{value}</span>
    </div>
  );
}
