import { Check } from "lucide-react";
import s from "./Pill.module.css";

export type PillOption = { value: string; label: string };

type Single = { mode: "single"; value: string | null; onChange: (v: string | null) => void };
type Multi = { mode: "multi"; value: string[]; onChange: (v: string[]) => void; max?: number | null };

type Props = (Single | Multi) & {
  options: PillOption[];
  label: string;               // the question; read by screen readers as the group's name
  hideLabel?: boolean;
  allowClear?: boolean;        // single: tapping the chosen pill again clears it
};

/** Big tappable options. Single works like radio buttons, multi like checkboxes with an optional cap (the cap
 * greys out the rest instead of silently dropping a choice). */
export function PillGroup(props: Props) {
  const { options, label, hideLabel } = props;
  const chosen = props.mode === "single" ? (props.value ? [props.value] : []) : props.value;
  const full = props.mode === "multi" && props.max != null && chosen.length >= props.max;

  function toggle(v: string) {
    if (props.mode === "single") {
      props.onChange(props.value === v && props.allowClear !== false ? null : v);
    } else {
      const on = props.value.includes(v);
      if (!on && full) return;
      props.onChange(on ? props.value.filter((x) => x !== v) : [...props.value, v]);
    }
  }

  return (
    <div role="group" aria-label={label} className={s.group}>
      {!hideLabel && <div className={s.legend}>{label}</div>}
      <div className={s.pills}>
        {options.map((o) => {
          const on = chosen.includes(o.value);
          const disabled = !on && full;
          return (
            <button
              key={o.value}
              type="button"
              role={props.mode === "single" ? "radio" : "checkbox"}
              aria-checked={on}
              disabled={disabled}
              className={[s.pill, on ? s.on : ""].join(" ")}
              onClick={() => toggle(o.value)}
            >
              {on && <Check size={16} strokeWidth={3} aria-hidden className={s.tick} />}
              {o.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
