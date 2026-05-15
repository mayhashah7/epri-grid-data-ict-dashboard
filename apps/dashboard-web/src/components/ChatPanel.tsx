import { useRef, useState, useEffect } from 'react';
import { chatStream } from '../lib/api';

type Msg = { role: 'user' | 'assistant' | 'tool'; text: string; meta?: any };
type Persona = 'operator' | 'planner' | 'customer';

const STARTERS: Record<Persona, string[]> = {
  operator: [
    'Are there any outages right now on substation S-01?',
    'Find suspicious meters that look like theft on S-02.',
    'Show me solar backfeed and Volt-VAR risk on S-04.',
    'Score transformer health on substation S-03.',
  ],
  planner: [
    'Plan a 5 MW demand response event for the next hour.',
    'Which transformers need urgent inspection on S-05?',
    'How many DER meters are over-voltage on S-04?',
    'Stage a heat-wave demand response across opt-in residential.',
  ],
  customer: [
    'Why was my August bill higher than July?',
    "Is my power back on? My meter is on substation S-01.",
    'Should I switch to a time-of-use tariff?',
    'How does my usage compare to my neighbors?',
  ],
};

type ChatPanelProps = { onAgentActive?: (name: string) => void };

export function ChatPanel({ onAgentActive }: ChatPanelProps = {}) {
  const [persona, setPersona] = useState<Persona>('operator');
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => { scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight); }, [msgs]);

  function changePersona(p: Persona) {
    if (p === persona) return;
    setPersona(p);
    setMsgs([]);   // clear prior session
    setText('');
  }

  async function send(t: string) {
    if (!t.trim() || busy) return;
    setMsgs(m => [...m, { role: 'user', text: t }]);
    setText(''); setBusy(true);
    try {
      let answered = false;
      for await (const evt of chatStream(t, persona)) {
        if (evt.type === 'tool_call') {
          setMsgs(m => [...m, { role: 'tool', text: `→ ${evt.name}(${JSON.stringify(evt.arguments).slice(0, 80)})` }]);
        } else if (evt.type === 'final') {
          setMsgs(m => [...m, { role: 'assistant', text: evt.text }]);
          answered = true;
        } else if (evt.type === 'tool_result' && evt.name === 'dispatch_to_agent' && onAgentActive) {
          onAgentActive(evt.result?.target_agent ?? '');
        }
      }
      if (!answered) setMsgs(m => [...m, { role: 'assistant', text: '(no answer returned)' }]);
    } catch (e: any) {
      setMsgs(m => [...m, { role: 'assistant', text: `error: ${e.message}` }]);
    } finally { setBusy(false); }
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-baseline justify-between mb-2 gap-2">
        <h2 className="text-sm font-semibold tracking-wide">CHAT</h2>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setMsgs([])}
            title="Clear chat"
            className="text-xs px-1.5 py-0.5 border border-grid-border rounded hover:border-grid-accent text-slate-400"
          >clear</button>
          <select
            value={persona}
            onChange={e => changePersona(e.target.value as Persona)}
            className="text-xs bg-grid-bg border border-grid-border rounded px-1 py-0.5"
          >
            <option value="operator">operator</option>
            <option value="planner">planner</option>
            <option value="customer">customer</option>
          </select>
        </div>
      </div>
      <div ref={scrollRef} className="flex-1 overflow-y-auto scroll-fade text-xs space-y-1.5 pr-1">
        {msgs.length === 0 && (
          <div className="space-y-1">
            <div className="text-slate-500 mb-1">As <span className="text-grid-accent">{persona}</span>, try:</div>
            {STARTERS[persona].map(s => (
              <button key={s} onClick={() => send(s)} className="block text-left text-xs text-grid-info hover:text-grid-accent">• {s}</button>
            ))}
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={
            m.role === 'user' ? 'text-slate-200 bg-grid-bg p-1.5 rounded'
            : m.role === 'tool' ? 'text-xs text-grid-info font-mono'
            : 'text-emerald-300 bg-emerald-500/10 p-1.5 rounded border border-emerald-500/20 whitespace-pre-wrap'
          }>
            {m.text}
          </div>
        ))}
      </div>
      <div className="mt-2 flex gap-1">
        <input
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send(text)}
          placeholder={busy ? 'thinking…' : `ask as ${persona}…`}
          disabled={busy}
          className="flex-1 bg-grid-bg border border-grid-border rounded px-2 py-1 text-xs"
        />
        <button onClick={() => send(text)} disabled={busy} className="px-2 py-1 text-xs rounded bg-grid-accent text-black disabled:opacity-50">↩</button>
      </div>
    </div>
  );
}
