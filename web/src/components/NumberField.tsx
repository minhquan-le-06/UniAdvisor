import { Minus, Plus } from "lucide-react";
import { useEffect, useId, useState } from "react";
import s from "./Field.module.css";

type Props = {
  label: string;
  value: number | null;
  onChange: (v: number | null) => void;
  min: number;
  max: number;
  step: number;
  placeholder?: string;
  hint?: string;
  suffix?: string;
  /** The - and + buttons (on by default; off for amounts like a budget, which are typed). */
  stepper?: boolean;
};

/** Vietnamese decimals ("8,5"), a stepper for thumbs, and a value kept inside [min, max]. An empty box is null. */
export function NumberField({ label, value, onChange, min, max, step, placeholder, hint, suffix, stepper = true }: Props) {
  const id = useId();
  const [text, setText] = useState(format(value));
  const [error, setError] = useState<string | null>(null);

  // Follow the value from outside (a loaded plan, the stepper) without rewriting what is being typed ("8," stays).
  useEffect(() => {
    setText((t) => (parse(t) === value ? t : format(value)));
  }, [value]);

  function commit(raw: string) {
    const t = raw.trim().replace(",", ".");
    if (t === "") { setError(null); onChange(null); return; }
    const n = Number(t);
    if (!Number.isFinite(n) || n < min || n > max) {
      setError(`Nhập số từ ${format(min)} đến ${format(max)}.`);
      return;
    }
    setError(null);
    onChange(round(n, step));
  }

  function bump(dir: 1 | -1) {
    const base = value ?? (dir > 0 ? min - step : max + step);
    onChange(Math.min(max, Math.max(min, round(base + dir * step, step))));
    setError(null);
  }

  return (
    <div className={s.field}>
      <label htmlFor={id} className={s.label}>{label}</label>
      <div className={[s.numberWrap, error ? s.invalid : ""].join(" ")}>
        {stepper && (
          <button type="button" className={s.step} onClick={() => bump(-1)} aria-label={`Giảm ${label}`}>
            <Minus size={18} strokeWidth={3} />
          </button>
        )}
        <input
          id={id}
          className={s.number}
          inputMode="decimal"
          autoComplete="off"
          value={text}
          placeholder={placeholder}
          aria-invalid={!!error}
          aria-describedby={hint || error ? `${id}-hint` : undefined}
          onChange={(e) => {
            setText(e.target.value);
            // A valid number counts at once (the bottom bar updates while typing); errors wait for the blur.
            const n = Number(e.target.value.trim().replace(",", "."));
            if (e.target.value.trim() && Number.isFinite(n) && n >= min && n <= max) { setError(null); onChange(round(n, step)); }
          }}
          onBlur={(e) => commit(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") commit((e.target as HTMLInputElement).value); }}
        />
        {suffix && <span className={s.suffix}>{suffix}</span>}
        {stepper && (
          <button type="button" className={s.step} onClick={() => bump(1)} aria-label={`Tăng ${label}`}>
            <Plus size={18} strokeWidth={3} />
          </button>
        )}
      </div>
      {(error || hint) && <div id={`${id}-hint`} className={error ? s.error : s.hint}>{error ?? hint}</div>}
    </div>
  );
}

export function format(v: number | null): string {
  if (v == null) return "";
  return String(Math.round(v * 100) / 100).replace(".", ",");
}

function parse(t: string): number | null {
  const n = Number(t.trim().replace(",", "."));
  return t.trim() && Number.isFinite(n) ? n : null;
}

function round(v: number, step: number): number {
  const decimals = (String(step).split(".")[1] ?? "").length;
  return Number(v.toFixed(Math.max(decimals, 2)));
}
