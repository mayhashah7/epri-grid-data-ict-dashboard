type Activity = { id: string; agent?: string; tool?: string; text?: string; ts: number };

export function ActivityFeed({ items }: { items: Activity[] }) {
  return (
    <div className="h-full flex flex-col">
      <div className="flex items-baseline justify-between mb-2">
        <h2 className="text-sm font-semibold tracking-wide">LIVE AGENT ACTIVITY</h2>
        <span className="text-xs text-slate-500">{items.length}</span>
      </div>
      <div className="flex-1 overflow-y-auto scroll-fade text-[11px] font-mono space-y-0.5 pr-1">
        {items.length === 0 && <div className="text-slate-500 text-xs">Waiting for agent activity… fire a scenario or ask in chat.</div>}
        {items.slice().reverse().map(it => (
          <div key={it.id} className="flex items-baseline gap-1.5 border-b border-grid-border/30 pb-0.5">
            <span className="text-slate-500 w-12 shrink-0">{new Date(it.ts).toLocaleTimeString().slice(0, 8)}</span>
            {it.tool ? (
              <>
                <span className="text-grid-info">→</span>
                <span className="text-grid-accent">{it.tool}</span>
                <span className="text-slate-500 truncate">{it.text}</span>
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
