import type { ReactNode } from "react";
import { Card } from "./Card";
import { Reveal } from "./Reveal";
import s from "./QCard.module.css";

type Props = {
  id: string;
  eyebrow: string;           // "Câu 3 · Về em"
  title?: string;
  hint?: string;
  eager?: boolean;           // shown before scrolling (the first cards)
  done?: boolean;            // answered: a tick in the corner
  children: ReactNode;
};

/** One question of the input page; it slides in when scrolled to. */
export function QCard({ id, eyebrow, title, hint, eager, done, children }: Props) {
  return (
    <Reveal eager={eager} id={id} className={s.wrap} data={{ q: title ?? eyebrow, done: done ? "1" : "0" }}>
      <Card tone="raised" as="section" className={s.card} aria-labelledby={title ? `${id}-t` : undefined}>
        <div className={s.head}>
          <span className="eyebrow">{eyebrow}</span>
          {done && <span className={s.done} aria-label="Đã trả lời">✓</span>}
        </div>
        {title && <h3 id={`${id}-t`} className={s.title}>{title}</h3>}
        {hint && <p className="small muted">{hint}</p>}
        <div className={s.body}>{children}</div>
      </Card>
    </Reveal>
  );
}

/** Scroll the next question into view after an answer (only when it is below the fold). */
export function goNext(id: string) {
  const next = document.getElementById(id);
  if (!next) return;
  const r = next.getBoundingClientRect();
  if (r.top > innerHeight * 0.7) {
    setTimeout(() => next.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" }), 180);
  }
}
