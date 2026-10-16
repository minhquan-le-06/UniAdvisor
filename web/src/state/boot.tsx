// Start-up: wait for the server (a free Space sleeps and takes 30-60 s to wake), ask for the access code when the
// server wants one, then load what every page needs (choices, fixed texts, the ngành names, an empty plan).
import { KeyRound, RefreshCw } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { ApiError, api, setAccessCode, setUnauthorizedHandler } from "../api/client";
import type { Meta, PlanJson } from "../api/types";
import { Button } from "../components/Button";
import { Callout } from "../components/Callout";
import { Card } from "../components/Card";
import { Blob, ProgressBar } from "../components/Decor";
import { PlanProvider } from "./plan";
import s from "./boot.module.css";

export type CatalogEntry = { code: string; label: string; level: string };
type Data = { meta: Meta; catalog: CatalogEntry[]; labels: Map<string, string> };

const DataCtx = createContext<Data | null>(null);

export function useData(): Data {
  const d = useContext(DataCtx);
  if (!d) throw new Error("useData outside Boot");
  return d;
}

type Phase = { kind: "loading" } | { kind: "waking"; since: number } | { kind: "code"; wrong: boolean }
  | { kind: "error"; text: string } | { kind: "ready"; data: Data; fresh: PlanJson };

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function Boot({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  const start = useCallback(async (cancelled: () => boolean) => {
    const t0 = Date.now();
    // Wait for the server: up to about 2 minutes, showing the waking screen after 1.5 s.
    for (let i = 0; ; i++) {
      try {
        await api.health();
        break;
      } catch (e) {
        if (cancelled()) return;
        if (Date.now() - t0 > 120_000) { setPhase({ kind: "error", text: (e as Error).message }); return; }
        if (Date.now() - t0 > 1500) setPhase({ kind: "waking", since: t0 });
        await sleep(Math.min(1000 + i * 500, 4000));
      }
    }
    // The first call that needs the data makes the server download and load it (some seconds): say so meanwhile.
    const slow = setTimeout(() => { if (!cancelled()) setPhase({ kind: "waking", since: t0 }); }, 1500);
    try {
      const [meta, catalog, fresh] = await Promise.all([api.meta(), api.catalog(), api.newPlan()]);
      clearTimeout(slow);
      if (cancelled()) return;
      setPhase({ kind: "ready", fresh, data: { meta, catalog, labels: new Map(catalog.map((c) => [c.code, c.label])) } });
    } catch (e) {
      clearTimeout(slow);
      if (cancelled()) return;
      if (e instanceof ApiError && e.status === 401) setPhase((p) => ({ kind: "code", wrong: p.kind === "code" }));
      else setPhase({ kind: "error", text: (e as Error).message });
    }
  }, []);

  useEffect(() => {
    let off = false;
    start(() => off);
    return () => { off = true; };
  }, [start, attempt]);

  useEffect(() => {
    setUnauthorizedHandler(() => setPhase((p) => (p.kind === "ready" ? { kind: "code", wrong: true } : p)));
    return () => setUnauthorizedHandler(null);
  }, []);

  if (phase.kind === "ready") {
    return (
      <DataCtx.Provider value={phase.data}>
        <PlanProvider fresh={phase.fresh}>{children}</PlanProvider>
      </DataCtx.Provider>
    );
  }
  return (
    <div className={s.screen}>
      <Blob color="var(--coral)" size={240} style={{ top: -60, right: -60 }} />
      <Blob color="var(--sun)" size={160} shape={1} style={{ bottom: -40, left: -40 }} />
      <div className={s.box}>
        <span className={s.logo}>UniAdvisor<span className={s.dot}>.</span></span>
        {phase.kind === "loading" && <div className={s.spinner} aria-label="Đang tải" role="status" />}
        {phase.kind === "waking" && <Waking since={phase.since} />}
        {phase.kind === "code" && <CodeForm wrong={phase.wrong} onDone={() => setAttempt((x) => x + 1)} />}
        {phase.kind === "error" && (
          <div className="stack">
            <Callout tone="err">{phase.text}</Callout>
            <Button icon={<RefreshCw size={18} />} onClick={() => { setPhase({ kind: "loading" }); setAttempt((x) => x + 1); }}>
              Thử lại
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

function Waking({ since }: { since: number }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, []);
  const secs = Math.round((now - since) / 1000);
  return (
    <div className="stack" role="status">
      <h2>Đang đánh thức máy chủ...</h2>
      <p className="muted">Máy chủ miễn phí tự ngủ khi lâu không có ai dùng. Lần đầu mở có thể mất 30–60 giây, em đợi chút nhé.</p>
      <ProgressBar value={Math.min(0.95, secs / 60)} label="Đang khởi động máy chủ" />
      <span className="small muted">{secs} giây</span>
    </div>
  );
}

function CodeForm({ wrong, onDone }: { wrong: boolean; onDone: () => void }) {
  const [code, setCode] = useState("");
  function submit(e: FormEvent) {
    e.preventDefault();
    if (!code.trim()) return;
    setAccessCode(code.trim());
    onDone();
  }
  return (
    <Card tone="raised">
      <form className="stack" onSubmit={submit}>
        <h2>Nhập mã truy cập</h2>
        <p className="muted">Bản thử nghiệm này cần mã truy cập. Mã chỉ được nhớ trong thẻ trình duyệt này.</p>
        {wrong && <Callout tone="err">Mã chưa đúng, em thử lại nhé.</Callout>}
        <label className="stack" style={{ gap: 6 }}>
          <span style={{ fontWeight: 600 }}>Mã truy cập</span>
          <input className={s.input} value={code} onChange={(e) => setCode(e.target.value)} autoFocus autoComplete="off" />
        </label>
        <Button type="submit" icon={<KeyRound size={18} />}>Vào</Button>
      </form>
    </Card>
  );
}
