// /phuong-an: the three recommended lists as cards, each with its pentagon; the one the pentagons favour is marked,
// and the details (the three shapes overlaid, the table of corners) are one tap away.
import { ArrowLeft, ArrowRight, Check, ListOrdered, Sparkles } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";
import { api } from "../api/client";
import type { Card as ListCardData, Missing, Recommend } from "../api/types";
import { Disclosure } from "../components/Accordion";
import { Button } from "../components/Button";
import { Callout } from "../components/Callout";
import { ErrorRetry } from "../components/ErrorRetry";
import { Card } from "../components/Card";
import { ListBadge, PickBadge } from "../components/Chips";
import { Pentagon } from "../components/Pentagon";
import { Reveal } from "../components/Reveal";
import { RichText } from "../components/RichText";
import { useToast } from "../components/Toast";
import { useServer } from "../features/lists/useServer";
import { WishCard } from "../features/lists/WishCard";
import { useData } from "../state/boot";
import { usePlan } from "../state/plan";
import { forServer } from "../state/planOps";
import s from "./Lists.module.css";

export default function Lists() {
  const { plan } = usePlan();
  const { data, error, loading, retry } = useServer<Recommend | Missing>(plan, (p, signal) => api.recommend(p, signal));
  const navigate = useNavigate();

  if (error && !data) return <ErrorRetry text={error} onRetry={retry} />;
  if (!data) return <ListsSkeleton />;
  if (data.missing.length) {
    const m = data as Missing;
    return (
      <div className="page stack">
        <Callout tone="info" title="Chưa đủ thông tin để lập danh sách">Em cần nhập: {m.missing_text.join("; ")}.</Callout>
        <Button icon={<ArrowLeft size={18} />} onClick={() => navigate(`/bat-dau?buoc=${m.missing.includes("shortlist") && m.missing.length === 1 ? 3 : 1}`)}>
          Quay lại nhập
        </Button>
      </div>
    );
  }
  return <ListsView r={data as Recommend} busy={loading} />;
}

function ListsView({ r, busy }: { r: Recommend; busy: boolean }) {
  const { plan, commit, setWords } = usePlan();
  const { meta } = useData();
  const navigate = useNavigate();
  const toast = useToast();
  const [choosing, setChoosing] = useState<string | null>(null);

  async function choose(priority: string) {
    setChoosing(priority);
    try {
      const res = await api.choose(forServer(plan), priority);
      commit(res.plan);
      setWords(res.words);
      navigate("/danh-sach");
    } catch (e) {
      toast((e as Error).message, "err");
    } finally {
      setChoosing(null);
    }
  }

  const current = plan.lists.chosen;
  return (
    <div className={s.page} aria-busy={busy}>
      <header className={s.head}>
        <span className="eyebrow">Bước cuối</span>
        <h1 className={s.h1}>Ba phương án gợi ý cho em</h1>
        <div className={s.intro}><RichText text={r.intro} /></div>
        {r.safe_line && <p className="small muted">{r.safe_line}</p>}
      </header>

      {current && (
        <Callout tone="info">
          Em đang dùng phương án {r.cards.find((c) => c.priority === current)?.name ?? ""}.{" "}
          <button type="button" className={s.link} onClick={() => navigate("/danh-sach")}>Xem danh sách của em</button>
        </Callout>
      )}
      {r.notes.map((n) => <Callout key={n} tone="info"><RichText text={n} /></Callout>)}

      {r.pick && (
        <Reveal eager>
          <div className={s.pick} role="note">
            <span className={s.spark} aria-hidden><Sparkles size={28} /></span>
            <div>
              <strong className={s.pickTitle}>Gợi ý cho em: {r.pick.name}</strong>
              <RichText text={r.pick.reason} />
              <p className="xs">Đây chỉ là gợi ý rút ra từ ba hình năm góc; em vẫn là người chọn.</p>
            </div>
          </div>
        </Reveal>
      )}

      <div className={s.cards}>
        {r.cards.map((c, i) => (
          <Reveal key={c.priority} index={i} eager>
            <ListCard c={c} chosen={current === c.priority} choosing={choosing} onChoose={choose} />
          </Reveal>
        ))}
      </div>

      {r.no_answers_note && <p className="small muted">{r.no_answers_note}</p>}

      <Reveal>
        <Disclosure title="Xem chi tiết: so sánh ba hình năm góc">
          <div className="stack">
            <p className="small muted">{meta.texts.pentagon_note}</p>
            <div className={s.overlay}>
              <Pentagon size={460} title="Ba phương án chồng lên nhau"
                        series={r.cards.filter((c) => c.pentagon && !c.blocked).map((c) => ({
                          label: c.name, color: `var(--list-${c.slot})`, values: c.pentagon!.values }))} />
            </div>
            <div className="row" style={{ justifyContent: "center" }}>
              {r.cards.map((c) => <ListBadge key={c.priority} slot={c.slot}>{c.name}</ListBadge>)}
            </div>
            <div className={s.tableWrap}>
              <table className={s.table}>
                <caption className="sr-only">Giá trị năm góc của ba phương án</caption>
                <thead><tr>{Object.keys(r.corner_rows[0] ?? {}).map((k) => <th key={k} scope="col">{k}</th>)}</tr></thead>
                <tbody>
                  {r.corner_rows.map((row) => (
                    <tr key={row["Góc"]}>{Object.entries(row).map(([k, v], j) => (j === 0 ? <th key={k} scope="row">{v}</th> : <td key={k}>{v}</td>))}</tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="xs muted">{r.at_least_one_text}</p>
          </div>
        </Disclosure>
      </Reveal>

      <Button variant="secondary" icon={<ArrowLeft size={18} />} onClick={() => navigate("/bat-dau")}>Sửa thông tin đã nhập</Button>
    </div>
  );
}

function ListCard({ c, chosen, choosing, onChoose }: {
  c: ListCardData; chosen: boolean; choosing: string | null; onChoose: (p: string) => void;
}) {
  return (
    <Card accent={`var(--list-${c.slot})`} tone="raised" as="article" className={[s.card, c.recommended ? s.recommended : ""].join(" ")}
          aria-label={`Phương án ${c.name}`}>
      <div className={s.cardHead}>
        <ListBadge slot={c.slot}>{c.name}</ListBadge>
        {c.recommended && <PickBadge />}
      </div>
      <div className={s.rowBody}>
      {c.pentagon && !c.blocked && (
        <div className={s.side}>
          <Pentagon size={300} series={[{ label: c.name, color: `var(--list-${c.slot})`, values: c.pentagon.values }]} title={`Năm góc của ${c.name}`} />
        </div>
      )}
      <div className={s.main}>
      <div className={s.fit}><RichText text={`Hợp nếu ${c.fit}.`} /></div>
      {c.blocked ? <Callout tone="warn">{c.blocked}</Callout> : (
        <>
          {c.same_as ? <div className="small"><RichText text={c.same_as} /></div> : (
            <ul className={s.pros}>
              {c.good.map((g) => <li key={g}><span className={s.yes} aria-label="Được">✔</span><span><RichText text={g} /></span></li>)}
              {c.bad.map((b) => <li key={b}><span className={s.no} aria-label="Đổi lại">✘</span><span><RichText text={b} /></span></li>)}
            </ul>
          )}
          {c.warning && <Callout tone="warn"><RichText text={c.warning} /></Callout>}
          {c.notes.map((n) => <div key={n} className="xs muted"><RichText text={n} /></div>)}
          {c.wish_items && (
            <Disclosure title={<span className="row"><ListOrdered size={18} /> Xem {c.n_wishes} nguyện vọng</span>}>
              <div className={s.miniList}>{c.wish_items.map((w) => <WishCard key={w.nv} w={w} compact />)}</div>
            </Disclosure>
          )}
          <div className={s.choose}>
            <Button block size="lg" variant={chosen ? "secondary" : "primary"} disabled={!!choosing}
                    icon={chosen ? <Check size={18} /> : undefined} iconEnd={chosen ? undefined : <ArrowRight size={18} />}
                    onClick={() => onChoose(c.priority)}>
              {choosing === c.priority ? "Đang lập danh sách..." : chosen ? "Đang dùng phương án này" : "Chọn phương án này"}
            </Button>
          </div>
        </>
      )}
      </div>
      </div>
    </Card>
  );
}

function ListsSkeleton() {
  return (
    <div className={s.page} aria-busy="true">
      <div className={s.head}><span className="eyebrow">Bước cuối</span><h1 className={s.h1}>Đang xếp ba phương án...</h1>
        <p className="muted">Ứng dụng đang thử 20.000 năm điểm chuẩn giả lập cho mỗi phương án.</p></div>
      <div className={s.cards}>{[0, 1, 2].map((i) => <div key={i} className={s.skeleton} style={{ animationDelay: `${i * 120}ms` }} />)}</div>
    </div>
  );
}
