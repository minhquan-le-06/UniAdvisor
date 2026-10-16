// /bat-dau: what the student enters, as three steps (Về em · Chọn ngành · Hướng học), one open at a time (?buoc=1..3).
// Inside a step the questions slide in while scrolling and a small rail beside them shows which are answered. The
// header shows the three steps (PartsNav); a one-line bottom bar moves between steps and, at the end, leads to the
// three lists. It steps aside while the on-screen keyboard is open.
import { ArrowLeft, ArrowRight } from "lucide-react";
import { useEffect } from "react";
import { useNavigate } from "react-router";
import { Button } from "../components/Button";
import { useKeyboardOpen } from "../components/useScroll";
import { MajorsSection } from "../features/majors/MajorsSection";
import { OrderSection } from "../features/majors/OrderSection";
import { ProfileSection } from "../features/profile/ProfileSection";
import { StepRail } from "../features/profile/StepRail";
import { useStep } from "../features/profile/useStep";
import { usePlan } from "../state/plan";
import { missingLocal } from "../state/planOps";
import s from "./Input.module.css";

const MISSING = { scores: "điểm các môn", home_province: "tỉnh/thành", shortlist: "hướng học 1" };
const NEXT = ["Chọn ngành", "Xếp hướng học"];

export default function Input() {
  const { plan } = usePlan();
  const navigate = useNavigate();
  const [step, go] = useStep();
  const keyboard = useKeyboardOpen();
  // What the open step still needs before moving on.
  const missing = missingLocal(plan).filter((m) => (step === 1 ? m !== "shortlist" : step === 3 ? m === "shortlist" : false));
  const needPick = step === 2 && plan.majors.picks.length === 0;
  const blocked = missing.length > 0 || needPick;

  useEffect(() => { document.getElementById("step-body")?.focus({ preventScroll: true }); }, [step]);

  return (
    <div className={s.page}>
      <div className={s.layout}>
        <StepRail rootId="step-body" step={step} />
        <div className={s.content}>
          <header className={s.intro}>
            <h1 className={s.h1}>Kể cho mình nghe về em</h1>
            <p className="muted">Mọi câu đều không bắt buộc, trừ điểm thi, tỉnh/thành và hướng học 1. Làm lần lượt 3 bước.</p>
          </header>

          <div id="step-body" tabIndex={-1} className={s.step}>
            {step === 1 && <ProfileSection />}
            {step === 2 && <MajorsSection />}
            {step === 3 && <OrderSection />}
          </div>
        </div>
      </div>

      <div className={[s.bottom, keyboard ? s.bottomAway : ""].join(" ")}>
        <div className={s.bottomInner}>
          {step > 1 && (
            <Button variant="secondary" icon={<ArrowLeft size={18} />} onClick={() => go(step - 1)}>Quay lại</Button>
          )}
          {missing.length ? (
            <p className={s.missing}>Còn thiếu: <strong>{missing.map((m) => MISSING[m]).join(", ")}</strong></p>
          ) : needPick ? (
            <p className={s.missing}>Chọn ít nhất một ngành để xếp hướng học ở bước sau.</p>
          ) : (
            <p className={s.ready}>{step === 3 ? "Đủ thông tin rồi! 🎉" : `Xong bước ${step}!`}</p>
          )}
          {step < 3 ? (
            <Button disabled={blocked} iconEnd={<ArrowRight size={18} />} onClick={() => go(step + 1)}>
              Tiếp: {NEXT[step - 1]}
            </Button>
          ) : (
            <Button disabled={blocked} iconEnd={<ArrowRight size={18} />} onClick={() => navigate("/phuong-an")}>
              Xem 3 phương án
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
