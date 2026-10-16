import type { CSSProperties, HTMLAttributes } from "react";
import s from "./Card.module.css";

type Props = HTMLAttributes<HTMLDivElement> & {
  /** A coloured top edge, e.g. "var(--list-0)" for a phương án card. */
  accent?: string;
  tone?: "plain" | "tint" | "raised";
  as?: "div" | "section" | "article";
};

export function Card({ accent, tone = "plain", as: Tag = "div", className, style, ...rest }: Props) {
  const st = accent ? ({ ...style, "--card-accent": accent } as CSSProperties) : style;
  return <Tag className={[s.card, s[tone], accent ? s.accented : "", className ?? ""].join(" ")} style={st} {...rest} />;
}
