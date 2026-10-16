import { Check, Pencil, X } from "lucide-react";
import { useState } from "react";
import type { ChangeItem } from "../../api/types";
import { Button } from "../../components/Button";
import { Combobox } from "../../components/Combobox";
import { NumberField } from "../../components/NumberField";
import { PillGroup } from "../../components/Pill";
import { useData } from "../../state/boot";
import { useApply } from "../chosen/useApply";
import s from "./Chat.module.css";

/** The changes a message asked for. Each can be unticked; a missing detail (which school, which subject, how much)
 * is asked here; "Sửa" lets the student correct a number. Nothing changes before "Xác nhận". */
export function ChangeCard({ items, done, onClose }: { items: ChangeItem[]; done: boolean; onClose: (reply: string) => void }) {
  const { catalog } = useData();
  const { apply, busy } = useApply();
  const [on, setOn] = useState(items.map(() => true));
  const [values, setValues] = useState<Record<string, unknown>[]>(items.map(() => ({})));
  const [edit, setEdit] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (i: number, k: string, v: unknown) => setValues((vs) => vs.map((x, j) => (j === i ? { ...x, [k]: v } : x)));

  async function confirm() {
    const chosen = [], missing: string[] = [];
    for (const [i, it] of items.entries()) {
      if (!on[i]) continue;
      const params = { ...it.params };
      for (const p of it.open) {
        const v = values[i][p];
        if (v == null) missing.push(it.labels[p].replace(/\?$/, "").toLowerCase());
        else params[p] = v;
      }
      if (edit && values[i].fix != null) params.value = values[i].fix;
      chosen.push({ kind: it.kind, params, open: [], text: it.text });
    }
    if (missing.length) { setError(`Em chọn giúp mình: ${[...new Set(missing)].join(", ")}.`); return; }
    if (!chosen.length) { onClose("Không có thay đổi nào được chọn."); return; }
    const res = await apply(chosen, true);
    if (!res) return;
    const parts = [res.done.length ? `Đã áp dụng: ${res.done.join("; ")}.` : "", res.diff, ...res.errors].filter(Boolean);
    onClose(parts.join("\n\n") || "Không có gì thay đổi.");
  }

  return (
    <div className={[s.card, done ? s.cardDone : ""].join(" ")}>
      <strong>Các thay đổi sẽ áp dụng</strong>
      {items.map((it, i) => (
        <div key={i} className={s.change}>
          <label className={s.check}>
            <input type="checkbox" checked={on[i]} disabled={done} onChange={(e) => setOn((o) => o.map((x, j) => (j === i ? e.target.checked : x)))} />
            <span>{it.description}</span>
          </label>
          {!done && on[i] && it.open.map((p) => {
            const label = it.labels[p] ?? p;
            if (it.options[p]?.length) {
              return <PillGroup key={p} mode="single" label={label} value={(values[i][p] as string) ?? null}
                                options={it.options[p].map(([v, l]) => ({ value: String(v), label: l }))}
                                onChange={(v) => set(i, p, it.options[p].find(([x]) => String(x) === v)?.[0] ?? v)} />;
            }
            if (p === "code" || p === "new") {
              return <Combobox key={p} label={label} placeholder="Chọn ngành" value={(values[i][p] as string) ?? null}
                               options={catalog.filter((c) => p === "code" || c.level === "nganh").map((c) => ({ value: c.code, label: c.label }))}
                               onChange={(v) => set(i, p, v)} />;
            }
            const [min, max, step] = it.range;
            return <NumberField key={p} label={label} min={min} max={max} step={step} placeholder="nhập số"
                                value={(values[i][p] as number) ?? null} onChange={(v) => set(i, p, v)} />;
          })}
          {!done && on[i] && edit && !it.open.length && typeof it.params.value === "number" && (
            <NumberField label="Sửa giá trị" min={it.range[0]} max={it.range[1]} step={it.range[2]}
                         value={(values[i].fix as number) ?? (it.params.value as number)} onChange={(v) => set(i, "fix", v)} />
          )}
        </div>
      ))}
      {error && <p className={s.error} role="alert">{error}</p>}
      {!done && (
        <div className={s.cardActions}>
          <Button size="sm" icon={<Check size={16} />} onClick={confirm} disabled={busy}>{busy ? "Đang áp dụng..." : "Xác nhận"}</Button>
          <Button size="sm" variant="secondary" icon={<Pencil size={16} />} onClick={() => setEdit((x) => !x)}>Sửa</Button>
          <Button size="sm" variant="ghost" icon={<X size={16} />} onClick={() => onClose("Đã huỷ, danh sách giữ nguyên.")}>Huỷ</Button>
        </div>
      )}
    </div>
  );
}
