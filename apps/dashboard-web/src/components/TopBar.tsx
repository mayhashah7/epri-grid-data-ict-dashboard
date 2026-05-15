type Props = { systemKw: number; substations: number; foundry: boolean; agentCount: number };

export function TopBar({ systemKw, substations, foundry, agentCount }: Props) {
  const mw = (systemKw / 1000).toFixed(1);
  return (
    <header className="px-4 py-3 border-b border-grid-border bg-grid-panel flex items-center gap-6">
      <div className="flex items-center gap-2">
        <span className="text-grid-accent text-2xl">⚡</span>
        <h1 className="text-lg font-semibold tracking-wide">Grid Agentic Dashboard</h1>
        <span className="text-xs text-slate-500 ml-2">Power & Utilities · {agentCount}-Agent Foundry Fabric</span>
      </div>
      <div className="ml-auto flex items-center gap-6 text-xs font-mono">
        <Stat label="System Load" value={`${mw} MW`} accent />
        <Stat label="Substations" value={substations.toString()} />
        <Stat label="Agents" value={agentCount.toString()} accent />
        <Stat label="Foundry" value={foundry ? 'live' : 'mock'} accent={foundry} dim={!foundry} />
      </div>
    </header>
  );
}

function Stat({ label, value, accent, dim }: { label: string; value: string; accent?: boolean; dim?: boolean }) {
  return (
    <div className="flex flex-col items-end leading-tight">
      <span className="text-[10px] uppercase tracking-widest text-slate-500">{label}</span>
      <span className={`text-base ${accent ? 'text-grid-accent' : ''} ${dim ? 'text-slate-500' : ''}`}>{value}</span>
    </div>
  );
}
