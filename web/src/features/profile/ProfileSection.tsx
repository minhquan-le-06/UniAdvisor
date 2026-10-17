// "Về em": scores, where the student lives, priority, family. Every answer edits the plan at once.
import { useState } from "react";
import { Button } from "../../components/Button";
import { Combobox } from "../../components/Combobox";
import { HelpTip } from "../../components/HelpTip";
import { NumberField } from "../../components/NumberField";
import { PillGroup } from "../../components/Pill";
import { goNext, QCard } from "../../components/QCard";
import { useData } from "../../state/boot";
import { usePlan } from "../../state/plan";
import { electivesOf, setProfile, setScore } from "../../state/planOps";
import { HELP } from "./helpTexts";
import { useSchools } from "./useSchools";
import s from "../../pages/Input.module.css";

const SCORE = { min: 0, max: 10, strictStep: true };      // the step is the subject's (meta.score_steps); an odd one is refused
const COMMON_ELECTIVES = 8;

export function ProfileSection() {
  const { meta } = useData();
  const { plan, edit } = usePlan();
  const p = plan.profile;
  const name = Object.fromEntries(meta.subjects.map((x) => [x.code, x.name]));
  const electives = electivesOf(plan, meta.compulsory).filter(Boolean) as string[];
  const has = (c: string) => Number.isFinite(p.scores[c]);
  const stepOf = (code: string) => meta.score_steps[code] ?? meta.score_steps.default;
  const scoreProps = (code: string) => ({ ...SCORE, step: stepOf(code), jump: Math.max(stepOf(code), meta.score_steps.default) });
  const n = (i: number) => `Câu ${i} · Về em`;
  // The usual electives first; the rarer ones (other languages, technology) behind "Môn khác" unless already chosen.
  const [allElectives, setAllElectives] = useState(false);
  const shown = allElectives ? meta.electives
    : meta.electives.filter((c, i) => i < COMMON_ELECTIVES || electives.includes(c));

  // The school only helps fill khu vực: it is not kept in the plan, so it starts empty when a plan is opened again.
  const [school, setSchool] = useState<string | null>(null);
  const { schools, loading, error } = useSchools(p.home_province);
  const schoolOptions = [...new Map(schools.map((x) => [`${x.name}|${x.area}`, x])).values()]
    .map((x) => ({ value: `${x.name}|${x.area}`, label: x.name, hint: x.area }));
  const chosen = school ? schools.find((x) => `${x.name}|${x.area}` === school) ?? null : null;

  function pickSchool(v: string | null) {
    setSchool(v);
    const found = v ? schools.find((x) => `${x.name}|${x.area}` === v) : null;
    if (found) {
      edit((pl) => setProfile(pl, { area: found.area }));
      goNext("q-priority");
    }
  }

  function pickElectives(next: string[]) {
    edit((pl) => {
      const scores: Record<string, number> = {};
      for (const c of meta.compulsory) if (c in pl.profile.scores) scores[c] = pl.profile.scores[c];
      for (const c of next) scores[c] = c in pl.profile.scores ? pl.profile.scores[c] : NaN;
      return setProfile(pl, { scores });
    });
  }

  return (
    <div className={s.section} id="ve-em">
      <h2 className={s.sectionTitle}><span className={s.num}>1</span> Về em</h2>

      <QCard id="q-kind" eyebrow={n(1)} title="Điểm em nhập là điểm nào?" eager done>
        <PillGroup mode="single" label="Loại điểm" hideLabel allowClear={false} value={p.score_kind}
                   onChange={(v) => { if (v) edit((pl) => setProfile(pl, { score_kind: v as "expected" | "real" })); goNext("q-core"); }}
                   options={[{ value: "expected", label: "Điểm dự kiến (trước kỳ thi)" }, { value: "real", label: "Điểm thi thật (sau kỳ thi)" }]} />
      </QCard>

      <QCard id="q-core" eyebrow={n(2)} title="Điểm hai môn bắt buộc" hint="Thang 10. Toán chia nhỏ nhất 0,05; các môn khác 0,25." eager
             done={meta.compulsory.every(has)}>
        <div className={s.grid2}>
          {meta.compulsory.map((c) => (
            <NumberField key={c} label={name[c]} {...scoreProps(c)} placeholder="chưa nhập"
                         value={has(c) ? p.scores[c] : null} onChange={(v) => edit((pl) => setScore(pl, c, v))} />
          ))}
        </div>
      </QCard>

      <QCard id="q-elective" eyebrow={n(3)} title="Hai môn tự chọn em thi" eager done={electives.length === 2 && electives.every(has)}>
        <PillGroup mode="multi" max={meta.max_electives} label="Chọn 2 môn" value={electives} onChange={pickElectives}
                   options={shown.map((c) => ({ value: c, label: name[c] }))} />
        {meta.electives.length > COMMON_ELECTIVES && (
          <Button size="sm" variant="ghost" onClick={() => setAllElectives((x) => !x)}>
            {allElectives ? "Ẩn bớt môn" : `Môn khác (${meta.electives.length - COMMON_ELECTIVES})`}
          </Button>
        )}
        {electives.length > 0 && (
          <div className={s.grid2}>
            {electives.map((c) => (
              <NumberField key={c} label={`Điểm ${name[c]}`} {...scoreProps(c)} placeholder="chưa nhập"
                           value={has(c) ? p.scores[c] : null} onChange={(v) => edit((pl) => setScore(pl, c, v ?? NaN))} />
            ))}
          </div>
        )}
      </QCard>

      <QCard id="q-province" eyebrow={n(4)} title="Em đang ở tỉnh/thành nào?" done={!!p.home_province}
             hint="Dùng để xếp chương trình gần nhà nếu em muốn, và để tính khu vực ưu tiên.">
        <Combobox label="Tỉnh/thành" options={meta.provinces.map((x) => ({ value: x, label: x }))} value={p.home_province}
                  onChange={(v) => { edit((pl) => setProfile(pl, { home_province: v })); setSchool(null); if (!v) goNext("q-priority"); }}
                  placeholder="Chọn tỉnh/thành" />
        {p.home_province && (
          <>
            <Combobox label="Trường THPT em học (không bắt buộc)" options={schoolOptions} value={school}
                      onChange={pickSchool} placeholder={loading ? "Đang tải danh sách trường..." : "Chọn trường"}
                      searchPlaceholder="Gõ tên trường để tìm..." clearable
                      hint="Chọn trường để ứng dụng điền khu vực ưu tiên giúp em. Không thấy trường của em thì chọn “Trường THPT - Khu vực ...” hoặc tự chọn khu vực ở câu sau." />
            {error && <p className="small" role="alert">Chưa tải được danh sách trường. Em chọn khu vực ở câu sau nhé.</p>}
            {chosen && <p className="small" role="status">Trường này thuộc {chosen.area}, nên khu vực ưu tiên ở câu sau đã được chọn là {chosen.area}.</p>}
          </>
        )}
      </QCard>

      <QCard id="q-priority" eyebrow={n(5)} title="Khu vực và đối tượng ưu tiên" done
             hint="Không chắc thì giữ KV3 và không thuộc đối tượng ưu tiên; em sửa lại sau cũng được.">
        <div className={s.helpRow}>
          <PillGroup mode="single" label="Khu vực ưu tiên" allowClear={false} value={p.area}
                     onChange={(v) => v && edit((pl) => setProfile(pl, { area: v }))}
                     options={meta.areas.map((a) => ({ value: a.code, label: a.label }))} />
          <HelpTip label="Giải thích khu vực ưu tiên" title={HELP.area.title}>{HELP.area.body}</HelpTip>
        </div>
        <div className={s.helpRow}>
          <PillGroup mode="single" label="Đối tượng ưu tiên" allowClear={false} value={p.category}
                     onChange={(v) => v && edit((pl) => setProfile(pl, { category: v }))}
                     options={meta.categories.map((c) => ({ value: c.code, label: c.label }))} />
          <HelpTip label="Giải thích đối tượng ưu tiên" title={HELP.category.title}>{HELP.category.body}</HelpTip>
        </div>
      </QCard>

      <QCard id="q-year" eyebrow={n(6)} title="Năm em tốt nghiệp THPT" done>
        <NumberField label="Năm tốt nghiệp" min={meta.admission_year - 10} max={meta.admission_year} step={1}
                     value={p.graduation_year ?? meta.admission_year}
                     onChange={(v) => edit((pl) => setProfile(pl, { graduation_year: v == null || v === meta.admission_year ? null : Math.round(v) }))} />
      </QCard>

      <QCard id="q-budget" eyebrow={n(7)} title="Gia đình có thể chi học phí bao nhiêu mỗi năm?" done
             hint="Phương án “Tiết kiệm nhất” không chọn chương trình vượt ngân sách. Để trống nếu không giới hạn.">
        <NumberField label="Ngân sách" stepper={false} suffix="triệu/năm" min={1} max={1000} step={5} placeholder="không giới hạn"
                     value={p.budget_trieu} onChange={(v) => edit((pl) => setProfile(pl, { budget_trieu: v }))} />
      </QCard>

      <QCard id="q-near" eyebrow={n(8)} title="Em muốn học gần nhà không?" done>
        <PillGroup mode="single" label="Học gần nhà" hideLabel allowClear={false} value={p.near_home ? "yes" : "no"}
                   onChange={(v) => edit((pl) => setProfile(pl, { near_home: v === "yes" }))}
                   options={[{ value: "yes", label: "Có, ưu tiên gần nhà" }, { value: "no", label: "Không quan trọng" }]} />
      </QCard>

      <QCard id="q-favorite" eyebrow={n(9)} title="Trường em thích nhất (không bắt buộc)" done={!!p.favorite_school}
             hint="Chương trình của trường này được ưu tiên ở mọi mức, kể cả ngành khác ngành em chọn.">
        <Combobox label="Trường" clearable placeholder="Không chọn" value={p.favorite_school}
                  options={meta.schools.map((x) => ({ value: x.code, label: x.name, hint: x.code }))}
                  onChange={(v) => edit((pl) => setProfile(pl, { favorite_school: v }))} />
      </QCard>
    </div>
  );
}
