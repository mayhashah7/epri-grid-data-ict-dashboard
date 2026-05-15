// API base — at runtime, prefer same-origin (relative) so the deployed API can
// be reached via the dashboard's reverse-proxy or direct CORS.
const RUNTIME_API = (window as any).__AMI_API_BASE__ as string | undefined;
export const API_BASE = RUNTIME_API && RUNTIME_API.length > 0 ? RUNTIME_API : '';

export const WS_URL = (() => {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  if (API_BASE) return API_BASE.replace(/^http/, 'ws') + '/ws/stream';
  return `${proto}://${location.host}/ws/stream`;
})();

export type Substation = {
  substation_id: string; name: string; lat: number; lon: number;
  meter_count: number; offline_count: number; total_kw: number;
};

export type Meter = {
  meter_id: string; substation_id: string; feeder_id: string;
  transformer_id: string; persona: string; tariff: string;
  lat: number; lon: number; online: boolean; last_kw: number; last_voltage: number;
};

export type Case = {
  case_id: string; kind: string; status: string; summary: string;
  opened_at: string; closed_at: string | null;
  recommendation?: string | null; routed_to?: string;
};

export type Trace = {
  case_id: string; agent: string; step: string; status: string;
  payload: any; ts: string;
};

export async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} on ${path}`);
  return r.json() as Promise<T>;
}

export async function postJson<T>(path: string, body: any): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} on ${path}`);
  return r.json() as Promise<T>;
}

export async function* chatStream(text: string, persona: string, caseId?: string): AsyncGenerator<any> {
  const r = await fetch(`${API_BASE}/api/chat`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ text, persona, case_id: caseId }),
  });
  if (!r.body) throw new Error('no body');
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop() ?? '';
    for (const l of lines) {
      const t = l.trim();
      if (!t) continue;
      try { yield JSON.parse(t); } catch { /* ignore parse errors */ }
    }
  }
  if (buf.trim()) {
    try { yield JSON.parse(buf); } catch { /* */ }
  }
}
