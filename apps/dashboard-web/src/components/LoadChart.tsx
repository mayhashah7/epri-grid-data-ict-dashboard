import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip } from 'recharts';

export function LoadChart({ history }: { history: { ts: string; mw: number }[] }) {
  return (
    <div className="h-full flex flex-col">
      <div className="flex items-baseline justify-between mb-2">
        <h2 className="text-sm font-semibold tracking-wide">SYSTEM LOAD</h2>
        <span className="text-xs text-slate-500">last {history.length} ticks · 2s cadence</span>
      </div>
      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={history.map((h, i) => ({ i, mw: +h.mw.toFixed(2) }))}>
            <XAxis dataKey="i" hide />
            <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} width={50} unit=" MW" />
            <Tooltip contentStyle={{ background: '#0a0e1a', border: '1px solid #1f2937', fontSize: 12 }} labelStyle={{ color: '#94a3b8' }} />
            <Line type="monotone" dataKey="mw" stroke="#fbbf24" strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
