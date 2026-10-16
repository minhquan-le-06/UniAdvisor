// /_mau: every building block on one page, in the current theme, to agree on the style before the real pages.
// Only in `npm run dev` (main.tsx does not route it in a build).
import { ArrowRight, BookOpen, GraduationCap, MessageCircle, School, SlidersHorizontal, Sparkles, Target } from "lucide-react";
import { useState } from "react";
import { Disclosure } from "../components/Accordion";
import { Button } from "../components/Button";
import { Callout } from "../components/Callout";
import { Card } from "../components/Card";
import { LevelChip, ListBadge, PickBadge, Tag } from "../components/Chips";
import { Combobox } from "../components/Combobox";
import { Blob, ProgressBar } from "../components/Decor";
import { NumberField } from "../components/NumberField";
import { Pentagon } from "../components/Pentagon";
import { PillGroup } from "../components/Pill";
import { Reveal } from "../components/Reveal";
import { Sheet } from "../components/Sheet";
import { ThemeToggle } from "../components/ThemeToggle";
import { useToast } from "../components/Toast";
import s from "./StyleGuide.module.css";

const PROVINCES = ["Hà Nội", "TP. Hồ Chí Minh", "Đà Nẵng", "Hải Phòng", "Cần Thơ", "Nghệ An", "Thanh Hóa", "Đắk Lắk"]
  .map((p) => ({ value: p, label: p }));
const A = { hop_mon: 0.92, nguyen_vong_cao: 0.31, dung_nganh: 0.97, hoc_phi: 0.58, nghe_nghiep: null };
const B = { hop_mon: 1, nguyen_vong_cao: 0.18, dung_nganh: 0.74, hoc_phi: 0.66, nghe_nghiep: null };
const C = { hop_mon: 0.81, nguyen_vong_cao: 0.12, dung_nganh: 0.69, hoc_phi: 1, nghe_nghiep: null };

export default function StyleGuide() {
  const toast = useToast();
  const [kind, setKind] = useState<string | null>("expected");
  const [likes, setLikes] = useState<string[]>(["toán"]);
  const [math, setMath] = useState<number | null>(8.5);
  const [province, setProvince] = useState<string | null>(null);
  const [sheet, setSheet] = useState(false);

  return (
    <div className={s.wrap}>
      <header className={s.top}>
        <span className={s.logo}>UniAdvisor<span className={s.dot}>.</span></span>
        <div className="row"><span className="small muted">Trang mẫu style</span><ThemeToggle /></div>
      </header>

      <section className={s.hero}>
        <Blob color="var(--coral)" size={260} style={{ top: -60, right: -70 }} />
        <Blob color="var(--sun)" size={170} shape={1} style={{ bottom: -50, left: -40 }} />
        <Blob color="var(--sky)" size={90} style={{ top: 40, left: "38%", opacity: 0.6 }} />
        <div className={s.heroText}>
          <span className="eyebrow">Tuyển sinh 2027</span>
          <h1>Chọn ngành, xếp <span className={s.hl}>15 nguyện vọng</span> trong 10 phút</h1>
          <p className={s.lead}>Nhập điểm, chọn ngành em thích. UniAdvisor xếp danh sách theo đúng luật của Bộ và giải thích từng nguyện vọng.</p>
          <div className="row">
            <Button size="lg" iconEnd={<ArrowRight size={20} />}>Bắt đầu</Button>
            <Button size="lg" variant="secondary">Mở kế hoạch đã lưu</Button>
          </div>
          <p className="xs muted">Thông tin em nhập không được lưu trên máy chủ.</p>
        </div>
      </section>

      <div className={s.steps}>
        {[[GraduationCap, "Nhập điểm", "var(--coral)"], [Target, "Chọn ngành", "var(--grape)"], [Sparkles, "Nhận 15 nguyện vọng", "var(--mint)"]].map(([Icon, text, c], i) => {
          const I = Icon as typeof GraduationCap;
          return (
            <Reveal key={i} index={i} eager>
              <Card tone="raised" className={s.step}>
                <span className={s.stepIcon} style={{ background: c as string }}><I size={26} color="#fff" /></span>
                <span className={s.stepNo}>Bước {i + 1}</span>
                <strong>{text as string}</strong>
              </Card>
            </Reveal>
          );
        })}
      </div>

      <h2 className={s.h}>Thẻ câu hỏi (trang nhập)</h2>
      <div className="stack">
        <Reveal eager>
          <Card tone="raised" className="stack">
            <span className="eyebrow">Câu 1 / 9 · Về em</span>
            <PillGroup mode="single" label="Điểm em nhập là" value={kind} onChange={setKind}
                       options={[{ value: "expected", label: "Điểm dự kiến (trước kỳ thi)" }, { value: "real", label: "Điểm thi thật" }]} />
          </Card>
        </Reveal>
        <Reveal>
          <Card tone="raised" className="stack">
            <span className="eyebrow">Câu 2 / 9 · Điểm thi</span>
            <div className={s.grid2}>
              <NumberField label="Toán" value={math} onChange={setMath} min={0} max={10} step={0.25} placeholder="chưa nhập" />
              <NumberField label="Ngữ văn" value={null} onChange={() => {}} min={0} max={10} step={0.25} placeholder="chưa nhập" />
            </div>
          </Card>
        </Reveal>
        <Reveal>
          <Card tone="raised" className="stack">
            <span className="eyebrow">Câu 4 / 9 · Nơi ở</span>
            <Combobox label="Tỉnh/thành nơi em ở" options={PROVINCES} value={province} onChange={setProvince} placeholder="Chọn tỉnh/thành" />
          </Card>
        </Reveal>
        <Reveal>
          <Card tone="raised" className="stack">
            <span className="eyebrow">Câu 1 / 12 · Sở thích</span>
            <PillGroup mode="multi" max={3} label="Em thích học môn nào nhất? (chọn tối đa 3)" value={likes} onChange={setLikes}
                       options={["Toán", "Vật lí", "Hóa học", "Sinh học", "Ngữ văn", "Lịch sử", "Tiếng Anh"].map((x) => ({ value: x.toLowerCase().slice(0, 4), label: x }))} />
          </Card>
        </Reveal>
      </div>

      <h2 className={s.h}>Ba phương án</h2>
      <Callout tone="ok" title="Gợi ý cho em: Đúng ngành nhất">Hợp tổ hợp môn mạnh nhất và đúng ngành em chọn nhiều nhất trong 3 phương án.</Callout>
      <div className={s.cards}>
        {[["Đúng ngành nhất", A, 0, true], ["Hợp môn học nhất", B, 1, false], ["Tiết kiệm nhất", C, 2, false]].map(([name, v, slot, pick], i) => (
          <Reveal key={i} index={i} eager>
            <Card accent={`var(--list-${slot})`} tone="raised" className={s.listCard}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <ListBadge slot={slot as number}>{name as string}</ListBadge>
                {pick ? <PickBadge /> : null}
              </div>
              <Pentagon series={[{ label: name as string, color: `var(--list-${slot})`, values: v as typeof A }]} />
              <p className="small muted"><em>Hợp nếu em muốn học đúng ngành đã chọn.</em></p>
              <ul className={s.pros}>
                <li><span className={s.yes}>✔</span> 11/15 nguyện vọng đúng ngành em chọn</li>
                <li><span className={s.no}>✘</span> Học phí trung bình cao hơn 4 triệu/năm</li>
              </ul>
              <Button block>Chọn phương án này</Button>
            </Card>
          </Reveal>
        ))}
      </div>
      <Card>
        <h3>So sánh chồng ba hình</h3>
        <div className={s.center}>
          <Pentagon series={[
            { label: "Đúng ngành nhất", color: "var(--list-0)", values: A },
            { label: "Hợp môn học nhất", color: "var(--list-1)", values: B },
            { label: "Tiết kiệm nhất", color: "var(--list-2)", values: C },
          ]} size={460} />
        </div>
        <div className="row" style={{ justifyContent: "center" }}>
          <ListBadge slot={0}>Đúng ngành nhất</ListBadge><ListBadge slot={1}>Hợp môn học nhất</ListBadge><ListBadge slot={2}>Tiết kiệm nhất</ListBadge>
        </div>
      </Card>

      <h2 className={s.h}>Nguyện vọng</h2>
      <div className="stack">
        {([["mo_uoc", 1, "Trường Đại học Bách khoa Hà Nội", "Khoa học Máy tính", "25,75", "28,10 · 27,85"],
           ["thu_suc", 4, "Trường Đại học Công nghệ, ĐHQGHN", "Công nghệ thông tin", "25,75", "26,40 · 25,90"],
           ["vua_suc", 9, "Học viện Công nghệ Bưu chính Viễn thông", "Kỹ thuật phần mềm", "25,75", "25,10 · 24,60"],
           ["an_toan", 14, "Trường Đại học Thủy lợi", "Công nghệ thông tin", "25,75", "22,90 · 22,15"]] as const).map(([lv, nv, school, prog, score, cut], i) => (
          <Reveal key={nv} index={i}>
            <Card className={s.wish}>
              <span className={s.nv}>NV{nv}</span>
              <div className={s.wishBody}>
                <div className="row"><LevelChip level={lv} /><Tag>Hà Nội</Tag></div>
                <strong>{prog}</strong>
                <span className="small muted">{school}</span>
                <div className={s.nums}>
                  <span><b>{score}</b><small>Điểm của em</small></span>
                  <span><b>{cut}</b><small>Điểm chuẩn 2025 · 2026</small></span>
                </div>
              </div>
              <Button variant="ghost" size="sm" icon={<BookOpen size={16} />} onClick={() => setSheet(true)}>Vì sao?</Button>
            </Card>
          </Reveal>
        ))}
      </div>

      <h2 className={s.h}>Khả năng trúng tuyển</h2>
      <Card className="stack">
        {[["Một nguyện vọng mơ ước", 0.06, "--lv-mo-uoc"], ["Thử sức trở lên", 0.33, "--lv-thu-suc"], ["Vừa sức trở lên", 0.81, "--lv-vua-suc"], ["Một nguyện vọng bất kỳ", 0.99, "--lv-an-toan"]].map(([t, p, c]) => (
          <div key={t as string} className={s.bar}>
            <div className="row" style={{ justifyContent: "space-between" }}><span>{t as string}</span><b>{(p as number) >= 0.99 ? "≥ 99%" : `${Math.round((p as number) * 100)}%`}</b></div>
            <ProgressBar value={p as number} label={t as string} color={`var(${c})`} />
          </div>
        ))}
      </Card>

      <h2 className={s.h}>Thông báo, nút, chi tiết</h2>
      <div className="stack">
        <Callout tone="info">Em đang dùng điểm dự kiến. Sau kỳ thi, em mở lại kế hoạch và thay bằng điểm thật.</Callout>
        <Callout tone="warn" title="Chưa đủ an toàn">Khả năng em không trúng tuyển nguyện vọng nào là khoảng 12%.</Callout>
        <Callout tone="err">Không kết nối được máy chủ. Em thử lại sau ít phút nhé.</Callout>
        <div className="row">
          <Button icon={<SlidersHorizontal size={18} />}>Điều chỉnh</Button>
          <Button variant="secondary" icon={<School size={18} />}>Xem lại 3 phương án</Button>
          <Button variant="ghost">Hoàn tác</Button>
          <Button size="sm" variant="secondary" onClick={() => toast("Đã lưu kế hoạch về máy.", "ok")}>Thử thông báo</Button>
          <Button disabled>Đã chọn</Button>
        </div>
        <Disclosure title="Danh sách được lập thế nào?">
          <p className="small">Danh sách gồm tối đa 15 nguyện vọng, xếp theo một thứ tự cố định. Mỗi chương trình được xếp mức bằng cách so điểm của em với điểm chuẩn của hai năm gần nhất.</p>
        </Disclosure>
      </div>

      <button type="button" className={s.fab} aria-label="Mở chat" onClick={() => setSheet(true)}>
        <MessageCircle size={26} />
      </button>

      <Sheet open={sheet} onOpenChange={setSheet} title="Vì sao NV1 ở đây?" description="Trường Đại học Bách khoa Hà Nội · Khoa học Máy tính"
             footer={<Button block onClick={() => setSheet(false)}>Đã hiểu</Button>}>
        <div className="stack">
          <Callout tone="info" title="Mơ ước">Điểm của em thấp hơn điểm chuẩn thấp hơn của hai năm 2,1 điểm.</Callout>
          <ul className={s.pros}>
            <li>Điểm của em: 25,75 (A00, đã gồm 0,25 điểm ưu tiên)</li>
            <li>Điểm chuẩn 2025: 28,10 · 2026: 27,85</li>
            <li>Học phí: khoảng 32 triệu/năm</li>
          </ul>
          <p>Hệ thống xét từ NV1 xuống: nếu em đỗ NV1 thì các nguyện vọng sau không còn được xét.</p>
        </div>
      </Sheet>
    </div>
  );
}
