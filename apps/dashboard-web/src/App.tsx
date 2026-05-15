import { useEffect, useRef, useState } from 'react';
import { GridMap } from './components/GridMap';
import { LoadChart } from './components/LoadChart';
import { ScenarioPanel } from './components/ScenarioPanel';
import { CasePanel } from './components/CasePanel';
import { ChatPanel } from './components/ChatPanel';
import { TopBar } from './components/TopBar';
import { AgentRoster } from './components/AgentRoster';
import { ActivityFeed } from './components/ActivityFeed';
import { WS_URL, getJson, type Substation, type Case } from './lib/api';

type ActivityItem = { id: string; agent?: string; tool?: string; text: string; ts: number };

export default function App() {
  const [subs, setSubs] = useState<Substation[]>([]);
  const [cases, setCases] = useState<Case[]>([]);
  const [systemKw, setSystemKw] = useState<number>(0);
  const [tickHistory, setTickHistory] = useState<{ ts: string; mw: number }[]>([]);
  const [foundryConfigured, setFoundryConfigured] = useState<boolean>(false);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [activeAgents, setActiveAgents] = useState<Set<string>>(new Set());
  const decayTimers = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    getJson<{ foundry_configured: boolean }>('/api/health').then(h => setFoundryConfigured(h.foundry_configured)).catch(() => {});
    getJson<Substation[]>('/api/substations').then(setSubs).catch(console.error);
    getJson<Case[]>('/api/cases').then(setCases).catch(console.error);
  }, []);

  function pulseAgent(name: string) {
    setActiveAgents(prev => {
      const next = new Set(prev);
      next.add(name);
      return next;
    });
    const prev = decayTimers.current.get(name);
    if (prev) clearTimeout(prev);
    const t = window.setTimeout(() => {
      setActiveAgents(p => { const n = new Set(p); n.delete(name); return n; });
      decayTimers.current.delete(name);
    }, 4000);
    decayTimers.current.set(name, t);
  }

  function pushActivity(item: ActivityItem) {
    setActivity(prev => [...prev, item].slice(-200));
  }

  useEffect(() => {
    let ws: WebSocket | null = null;
    let stopped = false;
    function connect() {
      ws = new WebSocket(WS_URL);
      ws.onmessage = ev => {
        try {
          const m = JSON.parse(ev.data);
          if (m.type === 'tick') {
            setSystemKw(m.data.system_kw);
            const mw = m.data.system_kw / 1000;
            setTickHistory(h => {
              const next = [...h, { ts: m.data.ts, mw }];
              return next.length > 120 ? next.slice(next.length - 120) : next;
            });
            if (m.data.sub_totals_kw) {
              setSubs(prev => prev.map(s => ({ ...s, total_kw: m.data.sub_totals_kw[s.substation_id] ?? s.total_kw })));
            }
          } else if (m.type === 'case') {
            setCases(prev => {
              const others = prev.filter(c => c.case_id !== m.data.case_id);
              return [m.data, ...others].slice(0, 30);
            });
            if (m.data.routed_to) pulseAgent(m.data.routed_to);
            pulseAgent('ami-orchestrator');
          } else if (m.type === 'trace') {
            pulseAgent(m.data.agent);
            pushActivity({
              id: m.data.id ?? `${Date.now()}-${Math.random()}`,
              agent: m.data.agent,
              tool: m.data.step,
              text: m.data.agent.replace('ami-', ''),
              ts: Date.now(),
            });
          } else if (m.type === 'agent_activity') {
            const d = m.data;
            if (d.type === 'tool_call') {
              pushActivity({
                id: `${Date.now()}-${Math.random()}`,
                tool: d.name,
                text: JSON.stringify(d.arguments).slice(0, 60),
                ts: Date.now(),
              });
            } else if (d.type === 'final' || d.type === 'answer') {
              pushActivity({
                id: `${Date.now()}-${Math.random()}`,
                text: '✓ ' + (d.text ?? '').replace(/\n/g, ' ').slice(0, 80),
                ts: Date.now(),
              });
            }
          } else if (m.type === 'snapshot') {
            if (m.data.cases) setCases(m.data.cases);
          }
        } catch { /* ignore */ }
      };
      ws.onclose = () => { if (!stopped) setTimeout(connect, 2000); };
    }
    connect();
    return () => { stopped = true; ws?.close(); };
  }, []);

  return (
    <div className="h-full flex flex-col">
      <TopBar systemKw={systemKw} substations={subs.length} foundry={foundryConfigured} agentCount={12} />
      <div className="flex-1 grid grid-cols-12 grid-rows-12 gap-2 p-2 overflow-hidden">
        {/* Map - top left */}
        <div className="col-span-6 row-span-7 bg-grid-panel border border-grid-border rounded-xl overflow-hidden min-h-0">
          <GridMap substations={subs} />
        </div>

        {/* Agent Roster - top middle */}
        <div className="col-span-3 row-span-7 bg-grid-panel border border-grid-border rounded-xl p-3 overflow-hidden flex flex-col">
          <AgentRoster activeNames={activeAgents} />
        </div>

        {/* Chat - top right */}
        <div className="col-span-3 row-span-7 bg-grid-panel border border-grid-border rounded-xl p-3 overflow-hidden flex flex-col">
          <ChatPanel onAgentActive={pulseAgent} />
        </div>

        {/* Scenarios - bottom left wide */}
        <div className="col-span-6 row-span-3 bg-grid-panel border border-grid-border rounded-xl p-3 overflow-hidden">
          <ScenarioPanel onRan={() => getJson<Case[]>('/api/cases').then(setCases)} substations={subs} />
        </div>

        {/* Load chart - bottom middle */}
        <div className="col-span-3 row-span-3 bg-grid-panel border border-grid-border rounded-xl p-3 overflow-hidden">
          <LoadChart history={tickHistory} />
        </div>

        {/* Activity feed - bottom right */}
        <div className="col-span-3 row-span-3 bg-grid-panel border border-grid-border rounded-xl p-3 overflow-hidden">
          <ActivityFeed items={activity} />
        </div>

        {/* Cases - very bottom full width */}
        <div className="col-span-12 row-span-2 bg-grid-panel border border-grid-border rounded-xl p-3 overflow-hidden">
          <CasePanel cases={cases} layout="horizontal" />
        </div>
      </div>
    </div>
  );
}
