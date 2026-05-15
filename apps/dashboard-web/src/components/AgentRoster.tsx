import { useEffect, useState } from 'react';
import { getJson } from '../lib/api';

type Agent = {
  name: string; domain: string; icon: string; color: string;
  agent_id?: string | null; model?: string | null; registered?: boolean;
};

function modelBadgeColor(model?: string | null): string {
  if (!model) return 'text-slate-500 bg-slate-800/40';
  if (model.includes('gpt-5-chat')) return 'text-emerald-300 bg-emerald-900/30';
  if (model.includes('gpt-5-mini')) return 'text-cyan-300 bg-cyan-900/30';
  if (model.includes('gpt-5')) return 'text-fuchsia-300 bg-fuchsia-900/30';
  if (model.includes('gpt-4')) return 'text-amber-300 bg-amber-900/30';
  return 'text-slate-300 bg-slate-800/40';
}

export function AgentRoster({ activeNames }: { activeNames: Set<string> }) {
  const [agents, setAgents] = useState<Agent[]>([]);
  useEffect(() => { getJson<Agent[]>('/api/agents/roster').then(setAgents).catch(() => {}); }, []);

  const registered = agents.filter(a => a.registered).length;

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-baseline justify-between mb-2">
        <h2 className="text-sm font-semibold tracking-wide">AGENT FABRIC</h2>
        <span className="text-xs text-slate-500">{registered}/{agents.length} live in Foundry</span>
      </div>
      <div className="grid grid-cols-2 gap-1.5 overflow-y-auto scroll-fade pr-1">
        {agents.map(a => {
          const active = activeNames.has(a.name);
          return (
            <div
              key={a.name}
              className={`p-1.5 rounded-md border text-xs font-mono transition ${
                active
                  ? 'border-grid-accent bg-grid-accent/10 text-grid-accent shadow-[0_0_12px_rgba(251,191,36,0.4)]'
                  : 'border-grid-border bg-grid-bg text-slate-400'
              }`}
              title={`${a.name}${a.agent_id ? `\n${a.agent_id}` : ''}${a.model ? `\nmodel: ${a.model}` : ''}`}
            >
              <div className="flex items-center gap-1">
                <span style={{ color: a.color }} className="text-sm">{a.icon}</span>
                <span className="truncate">{a.name.replace('ami-', '')}</span>
                {active && <span className="ml-auto w-1.5 h-1.5 bg-grid-accent rounded-full animate-pulse" />}
              </div>
              <div className="flex items-center gap-1 mt-1">
                <span className={`px-1 rounded text-xs font-semibold ${modelBadgeColor(a.model)}`}>
                  {a.model || 'mock'}
                </span>
                {a.registered ? (
                  <span className="text-xs text-emerald-400">●live</span>
                ) : (
                  <span className="text-xs text-slate-600">○offline</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
