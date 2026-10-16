// "Điều chỉnh": the visible controls of the chosen list (the same changes the chat proposes), each applied on the
// server at once as one undo step.
import { ArrowLeftRight, RotateCcw, Save, Trash2, X } from "lucide-react";
import { useState } from "react";
import type { Controls } from "../../api/types";
import { Button } from "../../components/Button";
import { Combobox } from "../../components/Combobox";
import { NumberField } from "../../components/NumberField";
import { PillGroup } from "../../components/Pill";
import { Sheet } from "../../components/Sheet";
import { useData } from "../../state/boot";
import { MAX_CLOSE } from "../../state/planOps";
import { useApply } from "../chosen/useApply";
import s from "./Adjust.module.css";

export function AdjustSheet({ open, onOpenChange, c }: { open: boolean; onOpenChange: (o: boolean) => void; c: Controls }) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title="Điều chỉnh"
           description="Mỗi thay đổi được áp dụng ngay và danh sách lập lại; em có thể hoàn tác.">
      <div className={s.sections}>
        <ScoreAndPriority c={c} />
        <Budget c={c} />
        <Schools c={c} />
        <Remove c={c} />
        <Items c={c} />
      </div>
    </Sheet>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className={s.section}><h3 className={s.h}>{title}</h3>{children}</section>;
}

function ScoreAndPriority({ c }: { c: Controls }) {
  const { meta } = useData();
  const { apply, busy } = useApply();
  const name = Object.fromEntries(meta.subjects.map((x) => [x.code, x.name]));
  const electives = Object.keys(c.scores).filter((x) => !meta.compulsory.includes(x));
  const subjects = meta.subjects.map((x) => x.code)
    .filter((x) => meta.compulsory.includes(x) || electives.includes(x) || electives.length < meta.max_electives);
  const [subject, setSubject] = useState<string | null>(null);
  const [score, setScore] = useState<number | null>(null);
  const [area, setArea] = useState(c.area);
  const [category, setCategory] = useState(c.category);
  return (
    <Section title="Điểm và ưu tiên">
      <Combobox label="Môn" options={subjects.map((x) => ({ value: x, label: name[x], hint: c.scores[x] != null ? `hiện tại ${String(c.scores[x]).replace(".", ",")}` : undefined }))}
                value={subject} onChange={setSubject} placeholder="Chọn môn" />
      <NumberField label="Điểm mới" min={0} max={10} step={0.25} value={score} onChange={setScore} placeholder="chưa nhập" />
      <Button disabled={!subject || score == null || busy}
              onClick={() => apply([{ kind: "set_score", params: { subject, value: score } }]).then(() => setScore(null))}>Đổi điểm</Button>
      <PillGroup mode="single" label="Khu vực" allowClear={false} value={area} onChange={(v) => v && setArea(v)}
                 options={meta.areas.map((a) => ({ value: a.code, label: a.label }))} />
      <PillGroup mode="single" label="Đối tượng" allowClear={false} value={category} onChange={(v) => v && setCategory(v)}
                 options={meta.categories.map((x) => ({ value: x.code, label: x.label }))} />
      <Button variant="secondary" disabled={busy || (area === c.area && category === c.category)}
              onClick={() => apply([{ kind: "set_area", params: { value: area } }, { kind: "set_category", params: { value: category } }])}>
        Đổi ưu tiên
      </Button>
    </Section>
  );
}

function Budget({ c }: { c: Controls }) {
  const { apply, busy } = useApply();
  const [budget, setBudget] = useState<number | null>(null);
  const now = c.budget_trieu ? `${String(c.budget_trieu).replace(".", ",")} triệu/năm` : "không giới hạn";
  return (
    <Section title="Ngân sách và nơi học">
      <NumberField label={`Ngân sách (hiện tại: ${now})`} stepper={false} suffix="triệu/năm" min={1} max={1000} step={5} value={budget} onChange={setBudget} placeholder="triệu/năm" />
      <div className="row">
        <Button disabled={budget == null || busy} onClick={() => apply([{ kind: "set_budget", params: { value: budget } }]).then(() => setBudget(null))}>Đổi ngân sách</Button>
        <Button variant="secondary" disabled={c.budget_trieu == null || busy} onClick={() => apply([{ kind: "set_budget", params: { value: null } }])}>Bỏ giới hạn</Button>
      </div>
      <Button variant="secondary" disabled={busy} onClick={() => apply([{ kind: "set_near_home", params: { value: !c.near_home } }])}>
        {c.near_home ? "Tắt “muốn học gần nhà”" : "Bật “muốn học gần nhà”"}
      </Button>
    </Section>
  );
}

function Schools({ c }: { c: Controls }) {
  const { meta } = useData();
  if (!c.schools.length) return null;
  return (
    <Section title="Theo từng trường">
      <p className="xs muted">
        Điểm cộng: ứng dụng không biết quy định điểm cộng của từng trường (IELTS, chứng chỉ, học sinh giỏi...); em xem quy định
        của trường, tự tính rồi nhập. Điểm tự tính: điểm xét tuyển theo cách tính của trường, nhập theo thang điểm của trường;
        ứng dụng dùng điểm này thay cho tổng điểm thi ở trường đó. Điểm chuẩn chênh: nếu em thấy điểm chuẩn của trường thực ra
        cao hơn (+) hoặc thấp hơn (-), thang 30. Các điều chỉnh này chỉ áp dụng cho em.
      </p>
      {c.schools.map((x) => <SchoolRow key={x.code} x={x} maxShift={meta.limits.max_cutoff_shift} />)}
    </Section>
  );
}

function SchoolRow({ x, maxShift }: { x: Controls["schools"][number]; maxShift: number }) {
  const { apply, busy } = useApply();
  const [extra, setExtra] = useState<number | null>(x.extra);
  const [own, setOwn] = useState<number | null>(x.own);
  const [shift, setShift] = useState<number | null>(x.shift);
  const changed = (extra ?? 0) !== x.extra || own !== x.own || (shift ?? 0) !== x.shift;
  function save() {
    const items = [];
    if ((extra ?? 0) !== x.extra) items.push({ kind: "set_extra", params: { school: x.code, value: extra ?? 0 } });
    if (own !== x.own) items.push({ kind: "set_own_score", params: { school: x.code, value: own } });
    if ((shift ?? 0) !== x.shift) items.push({ kind: "set_cutoff_shift", params: { school: x.code, value: shift ?? 0 } });
    apply(items);
  }
  return (
    <details className={s.school}>
      <summary><span>{x.name}</span>{(x.extra || x.own != null || x.shift) ? <span className={s.dot} aria-label="có điều chỉnh" /> : null}</summary>
      <div className={s.schoolBody}>
        <NumberField label="Điểm cộng" min={0} max={10} step={0.25} value={extra} onChange={setExtra} />
        <NumberField label={`Điểm em tự tính${x.scales.length ? ` (thang ${x.scales.join(", ")})` : ""}`} min={0} max={100} step={0.05}
                     value={own} onChange={setOwn} placeholder="không dùng" />
        <NumberField label="Điểm chuẩn cao hơn (+) / thấp hơn (-)" min={-maxShift} max={maxShift} step={0.25} value={shift} onChange={setShift} />
        <Button size="sm" icon={<Save size={16} />} disabled={!changed || busy} onClick={save}>Lưu</Button>
      </div>
    </details>
  );
}

function Remove({ c }: { c: Controls }) {
  const { apply, busy } = useApply();
  const [school, setSchool] = useState<string | null>(null);
  const [program, setProgram] = useState<string | null>(null);
  return (
    <Section title="Bỏ trường hoặc nguyện vọng">
      <Combobox label="Trường" options={c.schools.map((x) => ({ value: x.code, label: x.name }))} value={school} onChange={setSchool} placeholder="Chọn trường" />
      <Button variant="secondary" icon={<Trash2 size={16} />} disabled={!school || busy}
              onClick={() => apply([{ kind: "remove_school", params: { school } }]).then(() => setSchool(null))}>Bỏ trường</Button>
      <Combobox label="Nguyện vọng" options={c.wishes.map((w) => ({ value: w.id, label: w.label }))} value={program} onChange={setProgram} placeholder="Chọn nguyện vọng" />
      <Button variant="secondary" icon={<Trash2 size={16} />} disabled={!program || busy}
              onClick={() => apply([{ kind: "remove_program", params: { program } }]).then(() => setProgram(null))}>Bỏ nguyện vọng</Button>
      {(c.removed_schools.length > 0 || c.removed_programs.length > 0) && (
        <div className={s.removed}>
          <span className="small" style={{ fontWeight: 600 }}>Đã bỏ</span>
          {c.removed_schools.map((x) => (
            <Button key={x.code} size="sm" variant="ghost" icon={<RotateCcw size={16} />} disabled={busy}
                    onClick={() => apply([{ kind: "restore_school", params: { school: x.code } }])}>Đưa lại {x.name}</Button>
          ))}
          {c.removed_programs.map((x) => (
            <Button key={x.id} size="sm" variant="ghost" icon={<RotateCcw size={16} />} disabled={busy}
                    onClick={() => apply([{ kind: "restore_program", params: { program: x.id } }])}>Đưa lại {x.label}</Button>
          ))}
        </div>
      )}
    </Section>
  );
}

function Items({ c }: { c: Controls }) {
  const { catalog } = useData();
  const { apply, busy } = useApply();
  const [index, setIndex] = useState<string | null>(null);
  const [code, setCode] = useState<string | null>(null);
  const [adding, setAdding] = useState<Record<number, string | null>>({});
  const nganh = catalog.filter((x) => x.level === "nganh");
  const slots = c.shortlist.map((e, i) => ({ value: String(i), label: `Hướng học ${i + 1}: ${e.label}` }));
  if (c.shortlist.length < 2) slots.push({ value: String(c.shortlist.length), label: "Thêm làm hướng học 2" });
  return (
    <Section title="Hướng học">
      {c.shortlist.length === 2 && (
        <Button variant="secondary" icon={<ArrowLeftRight size={16} />} disabled={busy} onClick={() => apply([{ kind: "swap_items" }])}>
          Đổi thứ tự hai hướng học
        </Button>
      )}
      <Combobox label="Thay" options={slots} value={index} onChange={setIndex} placeholder="Chọn hướng học" />
      <Combobox label="bằng ngành" options={catalog.map((x) => ({ value: x.code, label: x.label }))} value={code} onChange={setCode} placeholder="Chọn ngành" />
      <Button disabled={index == null || !code || busy}
              onClick={() => apply([{ kind: "replace_item", params: { index: Number(index), code } }]).then(() => { setIndex(null); setCode(null); })}>Thay</Button>
      {c.shortlist.map((e, i) => (
        <div key={e.main} className={s.closeBox}>
          <span className="small" style={{ fontWeight: 600 }}>Ngành gần của hướng học {i + 1} ({e.label}), tối đa {MAX_CLOSE}</span>
          <div className="row">
            {e.close.map((x) => (
              <span key={x.code} className={s.chip}>
                {x.label}
                <button type="button" aria-label={`Bỏ ngành gần ${x.label}`} disabled={busy}
                        onClick={() => apply([{ kind: "set_close", params: { index: i, old: x.code, new: null } }])}><X size={14} /></button>
              </span>
            ))}
            {!e.close.length && <span className="small muted">Không có</span>}
          </div>
          {e.close.length < MAX_CLOSE && (
            <>
              <Combobox label="Thêm ngành gần" value={adding[i] ?? null} onChange={(v) => setAdding((a) => ({ ...a, [i]: v }))} placeholder="Chọn ngành"
                        options={nganh.filter((x) => x.code !== e.main && !e.close.some((y) => y.code === x.code)).map((x) => ({ value: x.code, label: x.label }))} />
              <Button size="sm" variant="secondary" disabled={!adding[i] || busy}
                      onClick={() => apply([{ kind: "set_close", params: { index: i, old: null, new: adding[i] } }]).then(() => setAdding((a) => ({ ...a, [i]: null })))}>
                Thêm
              </Button>
            </>
          )}
        </div>
      ))}
    </Section>
  );
}
