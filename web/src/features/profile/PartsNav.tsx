// The three steps of the input page (Về em · Chọn ngành · Hướng học), shown inside the header while on that page: a dot
// per step (ticked when it has what the list needs), the open one highlighted, and a thin progress line.
import { usePlan } from "../../state/plan";
import { missingLocal } from "../../state/planOps";
import { useStep } from "./useStep";
import s from "./PartsNav.module.css";

export const PARTS = [
  { id: "ve-em", label: "Về em" },
  { id: "chon-nganh", label: "Chọn ngành" },
  { id: "huong-hoc", label: "Hướng học" },
];

export function PartsNav() {
  const { plan } = usePlan();
  const [step, go] = useStep();
  const missing = missingLocal(plan);
  const done = [
    !missing.includes("scores") && !missing.includes("home_province"),
    plan.majors.picks.length > 0,
    plan.majors.shortlist.length > 0,
  ];
  return (
    <nav className={s.nav} aria-label="Các bước">
      {PARTS.map((p, i) => (
        <a key={p.id} href={`?buoc=${i + 1}`} className={[s.part, done[i] ? s.done : "", step === i + 1 ? s.active : ""].join(" ")}
           aria-current={step === i + 1 ? "step" : undefined}
           onClick={(e) => { e.preventDefault(); go(i + 1); }}>
          <span className={s.dot}>{done[i] ? "✓" : i + 1}</span>
          <span className={s.label}>{p.label}</span>
        </a>
      ))}
      <span className={s.fill} style={{ width: `${(done.filter(Boolean).length / 3) * 100}%` }} aria-hidden />
    </nav>
  );
}
