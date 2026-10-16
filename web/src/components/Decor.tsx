import type { CSSProperties } from "react";
import s from "./Decor.module.css";

const SHAPES = [
  "M44.7,-61.3C56.9,-52.4,64.6,-37.4,69.3,-21.4C74,-5.4,75.7,11.6,69.8,25.6C63.9,39.6,50.4,50.6,35.6,58.7C20.8,66.8,4.7,72,-11.8,71.1C-28.3,70.2,-45.2,63.2,-56.7,51C-68.2,38.8,-74.3,21.4,-74.6,4.1C-74.9,-13.2,-69.4,-30.4,-58.3,-40.6C-47.2,-50.8,-30.5,-54,-15.4,-60.3C-0.3,-66.6,13.2,-76,27.5,-75.5C41.8,-75,56.9,-64.6,44.7,-61.3Z",
  "M38.9,-52.8C50.1,-45.2,58.5,-33.2,63.7,-19.4C68.9,-5.6,70.9,10,65.6,22.7C60.3,35.4,47.7,45.2,34.2,53.5C20.7,61.8,6.3,68.6,-9.4,69.9C-25.1,71.2,-42.1,67,-53.6,56.4C-65.1,45.8,-71.1,28.8,-71.8,12.3C-72.5,-4.2,-67.9,-20.2,-59.1,-32.5C-50.3,-44.8,-37.3,-53.4,-24,-60.2C-10.7,-67,2.9,-72,16.2,-69.6C29.5,-67.2,27.7,-60.4,38.9,-52.8Z",
];

/** A soft coloured shape for backgrounds (decoration only: hidden from screen readers). */
export function Blob({ color, size = 220, shape = 0, style, float = true }: {
  color: string; size?: number; shape?: 0 | 1; style?: CSSProperties; float?: boolean;
}) {
  return (
    <svg viewBox="-80 -80 160 160" width={size} height={size} aria-hidden className={[s.blob, float ? s.float : ""].join(" ")} style={style}>
      <path d={SHAPES[shape]} fill={color} />
    </svg>
  );
}

/** A bar that fills from the left; `value` 0-1. */
export function ProgressBar({ value, label, color = "var(--primary)" }: { value: number; label: string; color?: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div className={s.track} role="progressbar" aria-label={label} aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <div className={s.fill} style={{ width: `${pct}%`, background: color }} />
    </div>
  );
}
