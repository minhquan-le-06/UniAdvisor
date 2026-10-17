// The 12 questions ("Em chưa biết chọn gì"). One card per question, sliding in while the student scrolls. The server
// cleans the answers (caps, "not the same as question n"), reads the free text into guesses the student confirms, and
// suggests nhóm ngành; the cleaned answers go into the plan (they also drive the "Hợp sở thích nhất" list).
import { Check, Lightbulb, Plus, Sparkles } from "lucide-react";
import { useState } from "react";
import { api } from "../../api/client";
import type { QuizResult } from "../../api/types";
import { Button } from "../../components/Button";
import { Callout } from "../../components/Callout";
import { Card } from "../../components/Card";
import { PillGroup } from "../../components/Pill";
import { goNext, QCard } from "../../components/QCard";
import { Reveal } from "../../components/Reveal";
import { useToast } from "../../components/Toast";
import { useData } from "../../state/boot";
import { usePlan } from "../../state/plan";
import { addPick, MAX_PICKS, setAnswers } from "../../state/planOps";
import fs from "../../components/Field.module.css";
import s from "../../pages/Input.module.css";

type Picked = Record<string, string | string[] | null>;

export function Quiz() {
  const { meta } = useData();
  const { plan, edit } = usePlan();
  const toast = useToast();
  const qs = meta.questions;
  const [picked, setPicked] = useState<Picked>(() => ({ ...plan.majors.answers }));
  const [text, setText] = useState("");
  const [result, setResult] = useState<QuizResult | null>(null);
  const [keep, setKeep] = useState<string[]>([]);
  const [keepMaybe, setKeepMaybe] = useState<string[]>([]);       // the meaning-based guesses start unticked
  const [busy, setBusy] = useState(false);

  if (!qs.length) return <Callout tone="info">Chưa có dữ liệu để gợi ý ngành.</Callout>;

  async function run(next: Picked, freeText: string) {
    setBusy(true);
    try {
      const r = await api.questionnaire(next, freeText);
      setResult(r);
      setKeep(r.guesses.map((g) => `${g.question}:${g.option}`));
      setKeepMaybe([]);
      setPicked(r.answers);
      edit((p) => setAnswers(p, r.answers));
      setTimeout(() => document.getElementById("q-suggest")?.scrollIntoView({ behavior: "smooth", block: "start" }), 120);
    } catch (e) {
      toast((e as Error).message, "err");
    } finally {
      setBusy(false);
    }
  }

  function addGuesses() {
    if (!result) return;
    const next: Picked = { ...picked };
    for (const g of [...result.guesses, ...result.maybe]) {
      if (!keep.includes(`${g.question}:${g.option}`) && !keepMaybe.includes(`${g.question}:${g.option}`)) continue;
      const q = qs.find((x) => x.id === g.question);
      if (!q) continue;
      if (q.kind === "single") next[q.id] = g.option;
      else next[q.id] = [...new Set([...((next[q.id] as string[] | null) ?? []), g.option])];
    }
    run(next, "");
  }

  const answered = qs.filter((q) => { const v = picked[q.id]; return Array.isArray(v) ? v.length > 0 : !!v; }).length;

  return (
    <>
      {qs.map((q, i) => {
        const v = picked[q.id];
        const done = Array.isArray(v) ? v.length > 0 : !!v;
        const options = q.options.map((o) => ({ value: o.code, label: o.label }));
        const nextId = i + 1 < qs.length ? `q-quiz-${qs[i + 1].id}` : "q-quiz-text";
        return (
          <QCard key={q.id} id={`q-quiz-${q.id}`} eyebrow={`Câu ${q.number} / ${qs.length} · ${q.hint}`} title={q.text}
                 eager={i < 2} done={done}>
            {q.kind === "single" ? (
              <PillGroup mode="single" label={q.text} hideLabel value={(v as string) ?? null} options={options}
                         onChange={(x) => { setPicked((p) => ({ ...p, [q.id]: x })); if (x) goNext(nextId); }} />
            ) : (
              <PillGroup mode="multi" label={q.text} hideLabel max={q.max} value={(v as string[]) ?? []} options={options}
                         onChange={(x) => setPicked((p) => ({ ...p, [q.id]: x }))} />
            )}
          </QCard>
        );
      })}

      <QCard id="q-quiz-text" eyebrow="Thêm (không bắt buộc)" title="Kể thêm về em"
             hint="Ví dụ: em thích vẽ, hay giúp bạn học Toán, không thích ngồi một chỗ. Phần này không được lưu vào kế hoạch.">
        {meta.has_free_text && (
          <textarea className={fs.text} rows={3} maxLength={1000} value={text} onChange={(e) => setText(e.target.value)}
                    aria-label="Kể thêm về em" placeholder="Em thích..." />
        )}
      </QCard>

      <div className={s.suggestAction}>
        <Button size="lg" icon={<Lightbulb size={20} />} disabled={busy || (answered === 0 && !text.trim())}
                onClick={() => run(picked, text)}>
          {busy ? "Đang tính..." : "Xem gợi ý"}
        </Button>
        {answered === 0 && !text.trim() && <p className="small muted">Em trả lời vài câu rồi bấm “Xem gợi ý” nhé.</p>}
      </div>

      {result && (
        <div id="q-suggest" className="stack">
          {result.notes.map((n) => <Callout key={n} tone="info">{n}</Callout>)}
          {(result.guesses.length > 0 || result.maybe.length > 0) && (
            <Card tone="tint" className="stack">
              {result.guesses.length > 0 && (
                <>
                  <strong className="row"><Sparkles size={18} /> Từ phần em kể, ứng dụng đoán thêm:</strong>
                  <PillGroup mode="multi" label="Em bỏ chọn điều nào không đúng, rồi bấm “Thêm vào câu trả lời”."
                             value={keep} onChange={setKeep}
                             options={result.guesses.map((g) => ({ value: `${g.question}:${g.option}`, label: g.text }))} />
                </>
              )}
              {result.maybe.length > 0 && (
                <>
                  <strong className="row"><Sparkles size={18} /> Có thể em muốn nói:</strong>
                  <PillGroup mode="multi" label="Em chọn điều nào đúng ý em, rồi bấm “Thêm vào câu trả lời”."
                             value={keepMaybe} onChange={setKeepMaybe}
                             options={result.maybe.map((g) => ({ value: `${g.question}:${g.option}`, label: g.text }))} />
                </>
              )}
              <Button variant="secondary" icon={<Check size={18} />} onClick={addGuesses} disabled={busy}>Thêm vào câu trả lời</Button>
            </Card>
          )}
          {result.answered > 0 && <Suggestions result={result} />}
        </div>
      )}
    </>
  );
}

function Suggestions({ result }: { result: QuizResult }) {
  const { plan, edit } = usePlan();
  const { meta } = useData();
  const full = plan.majors.picks.length >= MAX_PICKS;
  return (
    <>
      <h3 className={s.subTitle}>Nhóm ngành có thể hợp với em</h3>
      {result.answered < 4 && <p className="small muted">Em mới trả lời ít câu; trả lời thêm sẽ cho gợi ý sát hơn.</p>}
      {result.suggestions.map((g, i) => {
        const picked = plan.majors.picks.includes(g.code);
        return (
          <Reveal key={g.code} index={i} eager>
            <Card tone="raised" className={s.suggest}>
              <span className={s.rank}>{i + 1}</span>
              <div className={s.hitText}>
                <strong>{g.label}</strong>
                {g.reasons.length > 0 && <span className="small">Vì em chọn: {g.reasons.join(", ")}</span>}
                <span className="xs muted">Gồm: {g.children.join(", ")}{g.more_children ? ", ..." : ""}</span>
              </div>
              <Button size="sm" variant={picked ? "secondary" : "primary"} disabled={picked || full}
                      icon={picked ? <Check size={16} /> : <Plus size={16} />} onClick={() => edit((p) => addPick(p, g.code))}>
                {picked ? "Đã chọn" : "Chọn"}
              </Button>
            </Card>
          </Reveal>
        );
      })}
      <p className="xs muted">{meta.texts.quiz_method_note}</p>
    </>
  );
}
