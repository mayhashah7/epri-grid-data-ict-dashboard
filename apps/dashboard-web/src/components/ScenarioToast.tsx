import { useEffect, useRef, useState } from 'react';

export interface ToastData {
  id: string;
  label: string;
  agent: string;
  hint: string;
}

const DURATION = 4500;

export function ScenarioToast({ toast }: { toast: ToastData | null }) {
  const [visible, setVisible] = useState(false);
  const [progress, setProgress] = useState(100);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rafRef = useRef<number | null>(null);
  const startRef = useRef(0);

  useEffect(() => {
    if (!toast) return;
    setVisible(true);
    setProgress(100);
    startRef.current = Date.now();
    if (timerRef.current) clearTimeout(timerRef.current);
    if (rafRef.current) cancelAnimationFrame(rafRef.current);

    const tick = () => {
      const pct = Math.max(0, 100 - ((Date.now() - startRef.current) / DURATION) * 100);
      setProgress(pct);
      if (pct > 0) rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    timerRef.current = setTimeout(() => setVisible(false), DURATION);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [toast?.id]);

  if (!visible || !toast) return null;

  return (
    <div className="fixed top-4 left-1/2 z-50 w-[440px] rounded-xl bg-grid-panel border border-grid-accent overflow-hidden shadow-[0_0_40px_rgba(251,191,36,0.25)] animate-slideDown">
      <div className="flex items-start gap-3 px-4 py-3">
        <span className="text-2xl mt-0.5">🤖</span>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-grid-accent">{toast.label} — injected</div>
          <div className="text-xs text-slate-400 mt-0.5">
            Dispatching <span className="text-grid-info font-mono">{toast.agent}</span>
          </div>
          <div className="text-xs text-slate-500 mt-0.5 truncate">{toast.hint}</div>
        </div>
        <button
          onClick={() => setVisible(false)}
          className="text-slate-500 hover:text-slate-300 text-sm leading-none mt-0.5"
        >✕</button>
      </div>
      {/* progress bar depletes over DURATION */}
      <div className="h-[3px] bg-grid-border">
        <div
          className="h-full bg-grid-accent"
          style={{ width: `${progress}%`, transition: 'width 50ms linear' }}
        />
      </div>
    </div>
  );
}
