import { ArrowRight, GraduationCap, ListChecks, MessageCircle, ShieldCheck, Sparkles, Target } from "lucide-react";
import { useNavigate } from "react-router";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { Blob } from "../components/Decor";
import { Reveal } from "../components/Reveal";
import { useOpenPlanFile } from "../components/AppShell";
import { useData } from "../state/boot";
import { usePlan } from "../state/plan";
import s from "./Landing.module.css";

const STEPS = [
  { icon: GraduationCap, color: "var(--coral)", title: "Nhập điểm", text: "Điểm dự kiến hoặc điểm thi thật, nơi em ở và ngân sách." },
  { icon: Target, color: "var(--grape)", title: "Chọn ngành", text: "Tìm ngành em thích, hoặc trả lời 12 câu hỏi để được gợi ý." },
  { icon: Sparkles, color: "var(--mint)", title: "Nhận 15 nguyện vọng", text: "Ba phương án xếp sẵn, kèm lý do cho từng nguyện vọng." },
];

const POINTS = [
  { icon: ListChecks, text: "Xếp theo đúng quy chế tuyển sinh, so với điểm chuẩn hai năm gần nhất." },
  { icon: MessageCircle, text: "Hỏi lại hoặc chỉnh danh sách bằng chat: “Toán em được 9”, “bỏ trường X”." },
  { icon: ShieldCheck, text: "Không cần tài khoản. Thông tin em nhập không được lưu trên máy chủ." },
];

export default function Landing() {
  const navigate = useNavigate();
  const openFile = useOpenPlanFile();
  const { meta } = useData();
  const { plan } = usePlan();
  const started = plan.majors.shortlist.length > 0 || Object.keys(plan.profile.scores).length > 0;

  return (
    <div className={s.page}>
      <section className={s.hero}>
        <Blob color="var(--coral)" size={300} style={{ top: -80, right: -90 }} />
        <Blob color="var(--sun)" size={190} shape={1} style={{ bottom: -60, left: -50 }} />
        <Blob color="var(--sky)" size={100} style={{ top: 50, left: "42%", opacity: 0.55 }} />
        <div className={s.heroText}>
          <span className="eyebrow">Tuyển sinh {meta.admission_year}</span>
          <h1>Chọn ngành, xếp <span className={s.hl}>15 nguyện vọng</span> trong 10 phút</h1>
          <p className={s.lead}>
            Nhập điểm, chọn ngành em thích. UniAdvisor xếp danh sách theo đúng luật tuyển sinh và giải thích vì sao từng
            nguyện vọng nằm ở đó.
          </p>
          <div className={s.ctas}>
            <Button size="lg" iconEnd={<ArrowRight size={20} />} onClick={() => navigate("/bat-dau")}>
              {started ? "Làm tiếp" : "Bắt đầu"}
            </Button>
            <Button size="lg" variant="secondary" onClick={openFile}>Mở kế hoạch đã lưu</Button>
          </div>
        </div>
      </section>

      <div className={s.steps}>
        {STEPS.map((st, i) => (
          <Reveal key={st.title} index={i} eager>
            <Card tone="raised" className={s.step}>
              <span className={s.stepIcon} style={{ background: st.color }}><st.icon size={26} color="#fff" aria-hidden /></span>
              <span className={s.stepNo}>Bước {i + 1}</span>
              <h2 className={s.stepTitle}>{st.title}</h2>
              <p className="small muted">{st.text}</p>
            </Card>
          </Reveal>
        ))}
      </div>

      <Reveal>
        <Card className={s.points}>
          {POINTS.map((p) => (
            <div key={p.text} className={s.point}>
              <p.icon size={22} aria-hidden className={s.pointIcon} />
              <span>{p.text}</span>
            </div>
          ))}
        </Card>
      </Reveal>
    </div>
  );
}
