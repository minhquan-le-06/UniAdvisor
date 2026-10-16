// /danh-sach: the list the student chose, rebuilt from the plan on every change: its pentagon, the 15 wishes with
// "Vì sao ở đây?", the chances, the notes; the chat button and the "Điều chỉnh" drawer change it, "Hoàn tác" undoes.
import { ArrowLeft, Download, SlidersHorizontal, Undo2 } from "lucide-react";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router";
import { api } from "../api/client";
import type { Chosen as ChosenData, Missing } from "../api/types";
import { Disclosure } from "../components/Accordion";
import { Button } from "../components/Button";
import { Callout } from "../components/Callout";
import { ErrorRetry } from "../components/ErrorRetry";
import { Card } from "../components/Card";
import { LevelChip, ListBadge } from "../components/Chips";
import { Pentagon } from "../components/Pentagon";
import { Reveal } from "../components/Reveal";
import { RichText } from "../components/RichText";
import { AdjustSheet } from "../features/adjust/AdjustSheet";
import { Chat, type ChatMsg } from "../features/chat/Chat";
import { ChanceBars } from "../features/chosen/ChanceBars";
import { ExplainSheet } from "../features/chosen/ExplainSheet";
import { useServer } from "../features/lists/useServer";
import { WishCard } from "../features/lists/WishCard";
import { useData } from "../state/boot";
import { usePlan } from "../state/plan";
import { forServer, unchoose } from "../state/planOps";
import s from "../features/chosen/Chosen.module.css";

export default function Chosen() {
  const { plan } = usePlan();
  const { data, error, loading, retry } = useServer<ChosenData | Missing>(plan, (p, signal) => api.chosen(p, signal));
  const [log, setLog] = useState<ChatMsg[]>([]);

  if (!plan.lists.chosen) return <Navigate to="/phuong-an" replace />;
  if (error && !data) return <ErrorRetry text={error} onRetry={retry} />;
  if (!data) return <div className={s.page}><div className={s.skeleton} aria-busy="true" /><div className={s.skeleton} /></div>;
  if (data.missing.length) return <Navigate to="/phuong-an" replace />;
  return (
    <>
      <ChosenView d={data as ChosenData} busy={loading} />
      <Chat log={log} setLog={(f) => setLog(f)} />
    </>
  );
}

function ChosenView({ d, busy }: { d: ChosenData; busy: boolean }) {
  const { plan, words, edit, undo, canUndo } = usePlan();
  const { meta } = useData();
  const navigate = useNavigate();
  const [explain, setExplain] = useState<number | null>(null);
  const [adjust, setAdjust] = useState(false);
  const h = d.header;

  function download() {
    const blob = new Blob([JSON.stringify(forServer(plan), null, 2) + "\n"], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "ke-hoach-uniadvisor.json";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  return (
    <div className={s.page} aria-busy={busy}>
      {h && (
        <Reveal eager>
          <Card accent={`var(--list-${h.slot})`} tone="raised" className={s.header}>
            {h.pentagon && (
              <div className={s.headerChart}>
                <Pentagon series={[{ label: h.name, color: `var(--list-${h.slot})`, values: h.pentagon.values }]} size={380} title={`Năm góc của ${h.name}`} />
              </div>
            )}
            <div className={s.headerText}>
              <span className="eyebrow">Phương án em chọn</span>
              <h1 className={s.h1}><ListBadge slot={h.slot}>{h.name}</ListBadge></h1>
              <p className="small muted">{cap(h.help)}.</p>
              {words && (
                <ul className={s.pros}>
                  {words.good.map((g) => <li key={g}><span className={s.yes} aria-label="Được">✔</span><span><RichText text={g} /></span></li>)}
                  {words.bad.map((b) => <li key={b}><span className={s.no} aria-label="Đổi lại">✘</span><span><RichText text={b} /></span></li>)}
                </ul>
              )}
              {h.fallback_note && <p className="xs muted">{h.fallback_note}</p>}
              {h.fees_note && <p className="xs muted">{h.fees_note}</p>}
              <div className={s.actions}>
                <Button icon={<SlidersHorizontal size={18} />} onClick={() => setAdjust(true)}>Điều chỉnh</Button>
                <Button variant="secondary" icon={<Undo2 size={18} />} disabled={!canUndo} onClick={undo}>Hoàn tác</Button>
                <Button variant="ghost" icon={<ArrowLeft size={18} />} onClick={() => { edit(unchoose); navigate("/phuong-an"); }}>
                  Xem lại 3 phương án
                </Button>
              </div>
            </div>
          </Card>
        </Reveal>
      )}

      <Callout tone="info">{meta.texts.extra_points_reminder}</Callout>
      {d.no_admission_warning && <Callout tone="warn" title="Chưa đủ an toàn">{d.no_admission_warning}</Callout>}
      {d.notes.map((n) => <Callout key={n} tone="warn"><RichText text={n} /></Callout>)}
      {d.favorite_note && <Callout tone="info">{d.favorite_note}</Callout>}
      {d.expected_note && <Callout tone="info">Em đang dùng điểm dự kiến. Sau kỳ thi, em mở lại kế hoạch và thay bằng điểm thật.</Callout>}

      <section className="stack" aria-labelledby="nv-title">
        <div className={s.sectionHead}>
          <h2 id="nv-title">{d.wish_items.length} nguyện vọng của em</h2>
          <div className={s.legend} aria-label="Các mức">
            {(["mo_uoc", "thu_suc", "vua_suc", "an_toan"] as const).map((lv) => <LevelChip key={lv} level={lv} />)}
          </div>
        </div>
        {d.empty ? <Callout tone="err">{d.empty_text}</Callout> : (
          <ol className={s.wishes}>
            {d.wish_items.map((w, i) => (
              <li key={w.program_id}><Reveal index={i % 4} eager={i < 3}><WishCard w={w} onExplain={setExplain} /></Reveal></li>
            ))}
          </ol>
        )}
        {d.mixed_method && <p className="xs muted">{meta.texts.mixed_method_note}</p>}
        <p className="xs muted">{d.score_caption}</p>
      </section>

      {d.chances && (
        <Reveal>
          <Card className="stack">
            <h2>Khả năng trúng tuyển</h2>
            <ChanceBars rows={d.chances.rows} />
            <p className="xs muted">{d.chances.note}</p>
          </Card>
        </Reveal>
      )}

      <Reveal>
        <div className="stack">
          <Disclosure title="Danh sách được lập thế nào?">
            <p className="small">{meta.texts.how_the_list_is_built}</p>
            <ul className={s.levels}>
              {meta.texts.levels.map((lv) => <li key={lv.code}><LevelChip level={lv.code as "mo_uoc"} /> {lv.help}.</li>)}
            </ul>
          </Disclosure>
          <Button variant="secondary" icon={<Download size={18} />} onClick={download}>Lưu kế hoạch về máy</Button>
        </div>
      </Reveal>

      <ExplainSheet nv={explain} onClose={() => setExplain(null)} />
      <AdjustSheet open={adjust} onOpenChange={setAdjust} c={d.controls} />
    </div>
  );
}

const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);
