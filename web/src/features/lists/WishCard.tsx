import { BookOpen, Heart, MapPin } from "lucide-react";
import type { WishItem } from "../../api/types";
import { Button } from "../../components/Button";
import { LevelChip, Tag } from "../../components/Chips";
import s from "./WishCard.module.css";

/** One nguyện vọng: its number, level, program, the student's score against the two cutoffs, fee and city.
 * `compact` (inside a phương án card) leaves out the relation line and the button. */
export function WishCard({ w, compact, onExplain }: { w: WishItem; compact?: boolean; onExplain?: (nv: number) => void }) {
  return (
    <article className={[s.wish, compact ? s.compact : ""].join(" ")} aria-label={`Nguyện vọng ${w.nv}: ${w.program}, ${w.school}`}>
      <span className={s.nv} style={{ background: `color-mix(in srgb, var(--lv-${w.level.replace("_", "-")}) 18%, var(--surface))` }}>
        <small>NV</small>{w.nv}
      </span>
      <div className={s.body}>
        <div className={s.tags}>
          <LevelChip level={w.level}>{cap(w.level_name)}</LevelChip>
          <Tag><MapPin size={12} aria-hidden style={{ marginRight: 3 }} />{w.city}</Tag>
          {w.favorite && <Tag><Heart size={12} aria-hidden style={{ marginRight: 3 }} />trường em thích</Tag>}
          {w.item === 2 && <Tag>hướng học 2</Tag>}
        </div>
        <strong className={s.program}>{w.program}{w.mixed && <span title="Xét kết hợp: xem chú thích dấu *"> *</span>}</strong>
        <span className={s.school}>{w.school}</span>
        {!compact && <span className="xs muted">{w.relation}{w.other_codes.length ? ` · cùng chương trình: mã ${w.other_codes.join(", ")}` : ""}</span>}
        <dl className={s.nums}>
          <div><dt>Điểm của em</dt><dd>{w.score}</dd></div>
          {w.cutoffs.map((c) => <div key={c.year}><dt>Điểm chuẩn {c.year}</dt><dd>{c.text}</dd></div>)}
          <div><dt>Học phí</dt><dd className={w.over_budget ? s.over : undefined}>{w.tuition}</dd></div>
        </dl>
      </div>
      {onExplain && (
        <Button variant="ghost" size="sm" icon={<BookOpen size={16} />} className={s.why} onClick={() => onExplain(w.nv)}>
          Vì sao ở đây?
        </Button>
      )}
    </article>
  );
}

const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);
