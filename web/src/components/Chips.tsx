import { Sparkles } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";
import s from "./Chips.module.css";

export type LevelCode = "mo_uoc" | "thu_suc" | "vua_suc" | "an_toan";
const LEVEL_NAME: Record<LevelCode, string> = { mo_uoc: "Mơ ước", thu_suc: "Thử sức", vua_suc: "Vừa sức", an_toan: "An toàn" };

/** The level of a wish: a coloured dot and its name (the name always shows). */
export function LevelChip({ level, children }: { level: LevelCode; children?: ReactNode }) {
  return (
    <span className={s.level} style={{ "--c": `var(--lv-${level.replace("_", "-")})` } as CSSProperties}>
      <span className={s.dot} aria-hidden />
      {children ?? LEVEL_NAME[level]}
    </span>
  );
}

/** The name of a phương án in its colour slot. */
export function ListBadge({ slot, children }: { slot: number; children: ReactNode }) {
  return (
    <span className={s.list} style={{ "--c": `var(--list-${slot})` } as CSSProperties}>
      <span className={s.swatch} aria-hidden />
      {children}
    </span>
  );
}

/** "Gợi ý" on the recommended card. */
export function PickBadge() {
  return (
    <span className={s.pick}>
      <Sparkles size={14} aria-hidden /> Gợi ý cho em
    </span>
  );
}

/** A small plain tag (a count, "*", "xa nhà"...). */
export function Tag({ children, tone = "plain" }: { children: ReactNode; tone?: "plain" | "warn" }) {
  return <span className={[s.tag, s[tone]].join(" ")}>{children}</span>;
}
