import { useEffect, useRef, useState } from 'react';
import { GridMap } from './components/GridMap';
import { LoadChart } from './components/LoadChart';
import { ScenarioPanel } from './components/ScenarioPanel';
import { CasePanel } from './components/CasePanel';
import { ChatPanel } from './components/ChatPanel';
import { TopBar } from './components/TopBar';
import { AgentRoster } from './components/AgentRoster';
import { ActivityFeed } from './components/ActivityFeed';
import { ScenarioToast, type ToastData } from './components/ScenarioToast';
import { WS_URL, getJson, postJson, type Substation, type Case } from './lib/api';

type ActivityItem = { id: string; agent?: string; tool?: string; text: string; ts: number };
type WsStatus = { connected: boolean; reconnecting: boolean };

export default function App() {
  const [subs, setSubs] = useState<Substation[]>([]);
  const [cases, setCases] = useState<Case[]>([]);
  const [systemKw, setSystemKw] = useState<number>(0);
  const [tickHistory, setTickHistory] = useState<{ ts: string; mw: number }[]>([]);
  const [foundryConfigured, setFoundryConfigured] = useState<boolean>(false);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [activeAgents, setActiveAgents] = useState<Set<string>>(new Set());
  const [wsStatus, setWsStatus] = useState<WsStatus>({ connected: false, reconnecting: false });
  const [toast, setToast] = useState<ToastData | null>(null);
  const decayTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const totalMeters = subs.reduce((s, sub) => s + sub.meter_count, 0);
  const offlineMeters = subs.reduce((s, sub) => s + sub.offline_count, 0);
  const onlineMetricsPct = totalMeters > 0 ? ((totalMeters - offlineMeters) / totalMeters) * 100 : 100;
  const activeCases = cases.filter(c => c.status !== 'resolved').length;
  const resolvedCases = cases.filter(c => c.status === 'resolved').length;

  useEffect(() => {
    getJson<{ foundry_configured: boolean }>('/api/health').then(h => setFoundryConfigured(h.foundry_configured)).catch(() => {});
    getJson<Substation[]>('/api/substations').then(setSubs).catch(console.error);
    getJson<Case[]>('/api/cases').then(setCases).catch(console.error);
  }, []);

  function pulseAgent(name: string) {
    setActiveAgents(prev => { const n = new Set(prev); n.add(name); return n; });
    const prev = decayTimers.current.get(name);
    if (prev) clearTimeout(prev);
    const t = setTimeout(() => {
      setActiveAgents(p => { const n = new Set(p); n.delete(name); return n; });
      decayTimers.current.delete(name);
    }, 4000);
    decayTimers.current.set(name, t);
  }

  function pushActivity(item: ActivityItem) {
    setActivity(prev => [...prev, item].slice(-200));
  }

  async function handleReset() {
    try {
      await postJson<any>('/api/reset', {});
      setCases([]);
      setActivity([]);
      setActiveAgents(new Set());
      const subs2 = await getJson<Substation[]>('/api/substations');
      setSubs(subs2);
    } catch { /* ignore */ }
  }

  useEffect(() => {
    let ws: WebSocket | null = null;
    let stopped = false;
    function connect() {
      setWsStatus({ connected: false, reconnecting: true });
      ws = new WebSocket(WS_URL);
      ws.onopen = () => setWsStatus({ connected: true, reconnecting: false });
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
            pulseAgent('ict-orchestrator');
          } else if (m.type === 'trace') {
            pulseAgent(m.data.agent);
            pushActivity({
              id: m.data.id ?? ${"$"}{Date.now()}-{Math.random()},
              agent: m.data.agent,
              tool: m.data.step,
              text: m.data.agent.replace(/^[a-z]+-/, ''),
              ts: Date.now(),
            });
          } else if (m.type === 'agent_activity') {
            const d = m.data;
            if (d.type === 'tool_call') {
              if (d.arguments?.target_agent) pulseAgent(d.arguments.target_agent);
              pushActivity({
                id: ${"$"}{Date.now()}-{Math.random()},
                tool: d.name,
                text: JSON.stringify(d.arguments ?? {}).slice(0, 60),
                ts: Date.now(),
              });
            } else if (d.type === 'final' || d.type === 'answer') {
              pushActivity({
                id: ${"$"}{Date.now()}-{Math.random()},
                text: '✓ ' + (d.text ?? '').replace(/\n/g, ' ').slice(0, 80),
                ts: Date.now(),
              });
            }
          } else if (m.type === 'snapshot') {
            if (m.data.cases) setCases(m.data.cases);
          }
        } catch { /* ignore */ }
      };
      ws.onclose = () => {
        setWsStatus({ connected: false, reconnecting: false });
        if (!stopped) setTimeout(connect, 2000);
      };
    }
    connect();
    return () => { stopped = true; ws?.close(); };
  }, []);

  return (
    <div className="h-full flex flex-col">
      <ScenarioToast toast={toast} />
      <TopBar
        systemKw={systemKw}
        substations={subs.length}
        foundry={foundryConfigured}
        agentCount={10}
        activeCases={activeCases}
        resolvedCases={resolvedCases}
        onlineMetricsPct={onlineMetricsPct}
        wsStatus={wsStatus}
        onReset={handleReset}
      />
      <div className="flex-1 grid grid-cols-12 grid-rows-12 gap-2 p-2 overflow-hidden">
        <div className="col-span-6 row-span-7 bg-grid-panel border border-grid-border rounded-xl overflow-hidden min-h-0">
          <GridMap substations={subs} />
        </div>
        <div className="col-span-3 row-span-7 bg-grid-panel border border-grid-border rounded-xl p-3 overflow-hidden flex flex-col">
          <AgentRoster activeNames={activeAgents} />
        </div>
        <div className="col-span-3 row-span-7 bg-grid-panel border border-grid-border rounded-xl p-3 overflow-hidden flex flex-col">
          <ChatPanel onAgentActive={pulseAgent} />
        </div>
        <div className="col-span-6 row-span-3 bg-grid-panel border border-grid-border rounded-xl p-3 overflow-hidden">
          <ScenarioPanel
            onRan={() => getJson<Case[]>('/api/cases').then(setCases)}
            substations={subs}
            onToast={setToast}
          />
        </div>
        <div className="col-span-3 row-span-3 bg-grid-panel border border-grid-border rounded-xl p-3 overflow-hidden">
          <LoadChart history={tickHistory} />
        </div>
        <div className="col-span-3 row-span-3 bg-grid-panel border border-grid-border rounded-xl p-3 overflow-hidden">
          <ActivityFeed items={activity} onClear={() => setActivity([])} />
        </div>
        <div className="col-span-12 row-span-2 bg-grid-panel border border-grid-border rounded-xl p-3 overflow-hidden">
          <CasePanel cases={cases} layout="horizontal" />
        </div>
      </div>
    </div>
  );
}
