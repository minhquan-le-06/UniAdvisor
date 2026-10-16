import type { ChanceRow } from "../../api/types";
import { ProgressBar } from "../../components/Decor";
import s from "./Chosen.module.css";

/** The chance of each level or better, one block per score shift (expected scores: 1 point lower, as entered, higher).
 * The percentage is always written next to its bar. */
export function ChanceBars({ rows }: { rows: ChanceRow[] }) {
  return (
    <div className={s.chanceGroups}>
      {rows.map((r) => (
        <div key={r.shift} className={[s.chanceGroup, r.shift === 0 ? s.chanceMain : ""].join(" ")}>
          <strong className="small">{r.label}</strong>
          {r.levels.map((lv) => (
            <div key={lv.level} className={s.bar}>
              <div className={s.barHead}><span className="small">{cap(lv.name)}</span><b>{lv.text}</b></div>
              <ProgressBar value={lv.p} label={`${r.label}: ${lv.name} ${lv.text}`} color={`var(--lv-${lv.level.replace("_", "-")})`} />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);
