// "Chọn ngành": two ways in (search, or the 12 questions), the tray of picked ngành, and their comparison.
import { BookOpen, Check, Compass, Plus, Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { MajorDetail, MajorHit } from "../../api/types";
import { Disclosure } from "../../components/Accordion";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { Tag } from "../../components/Chips";
import { QCard } from "../../components/QCard";
import { Reveal } from "../../components/Reveal";
import { useData } from "../../state/boot";
import { usePlan } from "../../state/plan";
import { addPick, MAX_PICKS, removePick } from "../../state/planOps";
import { Quiz } from "../quiz/Quiz";
import s from "../../pages/Input.module.css";

type Path = "search" | "quiz";

export function MajorsSection() {
  const { plan } = usePlan();
  const [path, setPath] = useState<Path>(() => (Object.keys(plan.majors.answers).length ? "quiz" : "search"));

  return (
    <div className={s.section} id="chon-nganh">
      <h2 className={s.sectionTitle}><span className={s.num}>2</span> Chọn ngành</h2>
      <Reveal>
        <div className={s.paths} role="radiogroup" aria-label="Em bắt đầu thế nào?">
          <PathCard on={path === "search"} onClick={() => setPath("search")} icon={<Search size={26} />}
                    title="Em đã có ngành quan tâm" text="Tìm và so sánh tối đa 6 ngành" color="var(--grape)" />
          <PathCard on={path === "quiz"} onClick={() => setPath("quiz")} icon={<Compass size={26} />}
                    title="Em chưa biết chọn gì" text="Trả lời 12 câu hỏi, khoảng 5 phút" color="var(--mint)" />
        </div>
      </Reveal>
      {path === "search" ? <MajorSearch /> : <Quiz />}
      <PickedTray />
    </div>
  );
}

function PathCard({ on, onClick, icon, title, text, color }: {
  on: boolean; onClick: () => void; icon: React.ReactNode; title: string; text: string; color: string;
}) {
  return (
    <button type="button" role="radio" aria-checked={on} onClick={onClick} className={[s.path, on ? s.pathOn : ""].join(" ")}>
      <span className={s.pathIcon} style={{ background: color }}>{icon}</span>
      <strong>{title}</strong>
      <span className="small muted">{text}</span>
    </button>
  );
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

function MajorSearch() {
  const { plan, edit } = usePlan();
  const [q, setQ] = useState("");
  const query = useDebounced(q.trim(), 250);
  const [hits, setHits] = useState<MajorHit[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!query) { setHits(null); return; }
    const ctl = new AbortController();
    api.searchMajors(query, ctl.signal).then((h) => { setHits(h); setError(null); })
      .catch((e) => { if (e.name !== "AbortError") setError(e.message); });
    return () => ctl.abort();
  }, [query]);

  const full = plan.majors.picks.length >= MAX_PICKS;
  return (
    <QCard id="q-search" eyebrow="Tìm ngành" title="Gõ tên ngành, tên viết tắt hoặc từ quen thuộc">
      <label className={s.searchBox}>
        <Search size={20} aria-hidden />
        <span className="sr-only">Tìm ngành</span>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ví dụ: CNTT, KHMT, logistics, bác sĩ"
               maxLength={100} autoComplete="off" />
        {q && <button type="button" onClick={() => setQ("")} aria-label="Xoá ô tìm"><X size={18} /></button>}
      </label>
      {error && <p className="small" style={{ color: "var(--err-ink)" }}>{error}</p>}
      {hits && hits.length === 0 && <p className="muted">Không tìm thấy ngành nào. Em thử cách gọi khác nhé.</p>}
      {hits && hits.length > 0 && (
        <ul className={s.hits} aria-live="polite">
          {hits.map((h, i) => {
            const picked = plan.majors.picks.includes(h.code);
            return (
              <li key={h.code} className={s.hit} style={{ animationDelay: `${i * 40}ms` }}>
                <div className={s.hitText}>
                  <strong>{h.label}</strong> <Tag>{h.kind}</Tag>
                  {h.official && <span className="xs muted">Tên Bộ GD&ĐT: {h.official}</span>}
                  {h.matched && <span className="xs muted">Khớp với tên chương trình ở trường: {h.matched}</span>}
                  {h.children.length > 0 && <span className="xs muted">Gồm: {h.children.join(", ")}{h.more_children ? ", ..." : ""}</span>}
                  <span className="xs muted">{h.where}</span>
                </div>
                <Button size="sm" variant={picked ? "secondary" : "primary"} disabled={picked || full}
                        icon={picked ? <Check size={16} /> : <Plus size={16} />} onClick={() => edit((p) => addPick(p, h.code))}>
                  {picked ? "Đã chọn" : "Chọn"}
                </Button>
              </li>
            );
          })}
        </ul>
      )}
    </QCard>
  );
}

function PickedTray() {
  const { plan, edit } = usePlan();
  const { labels } = useData();
  const picks = plan.majors.picks;
  return (
    <QCard id="q-picks" eyebrow={`Ngành em quan tâm · ${picks.length}/${MAX_PICKS}`} done={picks.length > 0}
           title={picks.length ? "Các ngành em đã chọn" : "Chưa có ngành nào"}
           hint={picks.length < 2 ? "Chọn từ 2 ngành trở lên để so sánh; hoặc xếp hướng học ngay bên dưới." : undefined}>
      {picks.length > 0 && (
        <div className={s.tray}>
          {picks.map((c) => (
            <span key={c} className={s.trayChip}>
              {labels.get(c) ?? c}
              <button type="button" onClick={() => edit((p) => removePick(p, c))} aria-label={`Bỏ ${labels.get(c) ?? c}`}><X size={16} /></button>
            </span>
          ))}
        </div>
      )}
      {picks.length >= 2 && <div className="stack">{picks.map((c) => <CompareCard key={c} code={c} />)}</div>}
    </QCard>
  );
}

const details = new Map<string, MajorDetail>();

function CompareCard({ code }: { code: string }) {
  const onet = useData().meta.texts.onet_credit;
  const [d, setD] = useState<MajorDetail | null>(details.get(code) ?? null);
  useEffect(() => {
    if (d) return;
    let off = false;
    api.major(code).then((x) => { details.set(code, x); if (!off) setD(x); }).catch(() => {});
    return () => { off = true; };
  }, [code, d]);
  if (!d) return <Card tone="tint" className={s.skeleton} aria-busy="true"><span className="sr-only">Đang tải</span></Card>;
  const pending = <span className="muted">Chưa có dữ liệu.</span>;
  const summary = [d.where, d.top_combos.length ? `tổ hợp hay gặp: ${d.top_combos.join(", ")}` : "",
                   d.interest_names.length ? `hợp với người thích ${d.interest_names.join(", ")}` : ""].filter(Boolean);
  return (
    <Card tone="tint" className="stack" style={{ gap: 8 }}>
      <div className="row"><strong>{d.label}</strong><Tag>{d.kind}</Tag></div>
      {d.official && <span className="xs muted">Tên Bộ GD&ĐT: {d.official}</span>}
      <span className="small muted">{summary.join(" · ")}</span>
      <Disclosure title={<span className="row"><BookOpen size={16} /> Xem chi tiết</span>}>
        <div className={s.facts}>
          <div><h4>Học gì</h4>{d.knowledge.length ? <p>Kiến thức chính: {d.knowledge.join(", ")}</p> : pending}
            {d.children.length > 0 && <p className="xs muted">Gồm: {d.children.join(", ")}</p>}</div>
          <div><h4>Cần mạnh môn nào</h4>{d.combos.length ? (
            <ul>{d.combos.map((c) => <li key={c.label}>{c.label} ({c.subjects.join(" - ")}): {c.share_pct}% chương trình</li>)}</ul>
          ) : pending}</div>
          <div><h4>Việc làm sau khi ra trường</h4>{d.jobs.length ? <p>{d.jobs.join("; ")}</p> : pending}
            <p className="xs muted">Thu nhập: {d.income}.</p></div>
          <div><h4>Có hợp với em không</h4>{d.interests.length ? (
            <p>Hợp với người thích: {d.interests.map((i) => (i.description ? `${i.name.toLowerCase()} (${i.description})` : i.name)).join("; ")}</p>
          ) : pending}{d.close.length > 0 && <p className="xs muted">Ngành gần: {d.close.join(", ")}</p>}</div>
        </div>
        {d.sheet && <Disclosure title="Bản tóm tắt nhóm ngành"><p className={s.sheet}>{d.sheet}</p></Disclosure>}
        {d.has_facts && <p className="xs muted" style={{ marginTop: 8 }}>{onet}{d.draft ? " Tên tiếng Việt và cách ghép ngành với nghề đang là bản nháp, chưa duyệt." : ""}</p>}
      </Disclosure>
    </Card>
  );
}
