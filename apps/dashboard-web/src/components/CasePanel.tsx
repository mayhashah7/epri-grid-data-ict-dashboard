import { useEffect, useState } from 'react';
import { getJson, type Case, type Trace } from '../lib/api';

const KIND_COLOR: Record<string, string> = {
  outage: 'bg-red-500/20 text-red-300 border-red-500/40',
  theft: 'bg-orange-500/20 text-orange-300 border-orange-500/40',
  der: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40',
  dr: 'bg-violet-500/20 text-violet-300 border-violet-500/40',
  maintenance: 'bg-sky-500/20 text-sky-300 border-sky-500/40',
  billing: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
  inquiry: 'bg-slate-500/20 text-slate-300 border-slate-500/40',
};

export function CasePanel({ cases, layout = 'vertical' }: { cases: Case[]; layout?: 'vertical' | 'horizontal' }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [traces, setTraces] = useState<Trace[]>([]);

  useEffect(() => {
    if (!openId) return;
    let live = true;
    const tick = () => getJson<Trace[]>(`/api/agents/traces?case_id=${openId}`).then(t => live && setTraces(t));
    tick();
    const id = setInterval(tick, 1500);
    return () => { live = false; clearInterval(id); };
  }, [openId]);

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-baseline justify-between mb-2">
        <h2 className="text-sm font-semibold tracking-wide">ACTIVE CASES</h2>
        <span className="text-xs text-slate-500">{cases.length}</span>
      </div>
      <div className={`overflow-auto flex-1 scroll-fade pr-1 ${layout === 'horizontal' ? 'flex gap-2' : 'space-y-2'}`}>
        {cases.length === 0 && <div className="text-xs text-slate-500">No cases yet — fire a scenario or ask in chat.</div>}
        {cases.map(c => (
          <div key={c.case_id} className={`rounded-lg border border-grid-border bg-grid-bg overflow-hidden ${layout === 'horizontal' ? 'min-w-[280px] max-w-[320px] shrink-0' : ''}`}>
            <button onClick={() => setOpenId(openId === c.case_id ? null : c.case_id)} className="w-full text-left p-2 hover:bg-grid-border/40">
              <div className="flex items-center gap-2">
                <span className={`text-[10px] px-1.5 py-0.5 rounded border ${KIND_COLOR[c.kind] ?? KIND_COLOR.inquiry}`}>{c.kind.toUpperCase()}</span>
                <span className="text-xs text-slate-400 font-mono truncate">{c.case_id}</span>
                <span className={`ml-auto text-[10px] ${c.status === 'resolved' ? 'text-grid-ok' : 'text-grid-warn'}`}>{c.status}</span>
              </div>
              <div className="text-sm mt-1 line-clamp-2">{c.summary}</div>
              {c.recommendation && <div className="text-[11px] text-slate-400 mt-1 line-clamp-2">↳ {c.recommendation}</div>}
            </button>
            {openId === c.case_id && (
              <div className="px-2 pb-2 border-t border-grid-border bg-black/30 max-h-56 overflow-y-auto">
                {traces.length === 0 && <div className="text-[11px] text-slate-500 py-1">no traces yet…</div>}
                {traces.map((t, i) => (
                  <div key={i} className="text-[11px] py-1 border-b border-grid-border/40 last:border-0">
                    <div className="flex items-center gap-2">
                      <span className="text-grid-info">{t.agent}</span>
                      <span className="text-slate-400">{t.step}</span>
                      <span className={`ml-auto ${t.status === 'resolved' ? 'text-grid-ok' : 'text-grid-warn'}`}>{t.status}</span>
                    </div>
                    {t.payload && Object.keys(t.payload).length > 0 && (
                      <pre className="text-[10px] text-slate-500 mt-0.5 whitespace-pre-wrap break-all font-mono">{JSON.stringify(t.payload).slice(0, 240)}</pre>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
