import type { CSSProperties } from "react";
import s from "./Pentagon.module.css";

export const CORNERS = ["hop_mon", "nguyen_vong_cao", "dung_nganh", "hoc_phi", "nghe_nghiep"] as const;
export type CornerCode = (typeof CORNERS)[number];
export const CORNER_NAME: Record<CornerCode, string> = {
  hop_mon: "Hợp môn", nguyen_vong_cao: "Nguyện vọng cao", dung_nganh: "Đúng ngành",
  hoc_phi: "Học phí phù hợp", nghe_nghiep: "Nghề nghiệp",
};

export type PentagonSeries = { label: string; color: string; values: Partial<Record<CornerCode, number | null>> };

type Props = {
  series: PentagonSeries[];          // one: a card; several: overlaid to compare
  size?: number;                     // width in px (height follows)
  labels?: boolean;                  // corner names and values around the shape
  title?: string;                    // accessible name
};

const W = 420, H = 330, CX = W / 2, CY = 168, R = 96;

function point(k: number, r: number): [number, number] {
  const a = Math.PI / 2 - (2 * Math.PI * k) / CORNERS.length;
  return [CX + r * R * Math.cos(a), CY - r * R * Math.sin(a)];
}

const pct = (v: number) => `${Math.round(v * 100)}%`;

/** Long names on two lines so the labels stay inside narrow cards. */
function lines(name: string): string[] {
  const w = name.split(" ");
  return w.length > 2 ? [w.slice(0, 2).join(" "), w.slice(2).join(" ")] : [name];
}

/** The five-corner view of a list: each corner 0-100%, further out is better. A corner without data is left out of
 * the shape and labelled "chưa có dữ liệu"; the shape needs at least three known corners. The numbers are also in the
 * labels (and in the table under the charts), so nothing is read from the shape alone. */
export function Pentagon({ series, size = 420, labels = true, title }: Props) {
  const grid = [0.25, 0.5, 0.75, 1].map((r) => CORNERS.map((_, k) => point(k, r).join(",")).join(" "));
  const one = series.length === 1 ? series[0] : null;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" className={s.svg} style={{ maxWidth: size }}
         aria-label={title ?? series.map((x) => x.label).join(", ")}>
      {grid.map((pts, i) => <polygon key={i} points={pts} className={s.grid} />)}
      {CORNERS.map((_, k) => {
        const [x, y] = point(k, 1);
        return <line key={k} x1={CX} y1={CY} x2={x} y2={y} className={s.grid} />;
      })}
      {series.map((sr, i) => {
        const known = CORNERS.map((c, k) => [k, sr.values[c]] as const).filter(([, v]) => v != null) as [number, number][];
        return (
          <g key={sr.label} className={s.shape}
             style={{ transformOrigin: `${CX}px ${CY}px`, animationDelay: `${i * 120}ms` } as CSSProperties}>
            {known.length >= 3 && (
              <polygon points={known.map(([k, v]) => point(k, v).join(",")).join(" ")}
                       fill={sr.color} fillOpacity={series.length > 1 ? 0.14 : 0.22} stroke={sr.color} strokeWidth={2.5}
                       strokeLinejoin="round" />
            )}
            {known.map(([k, v]) => {
              const [x, y] = point(k, v);
              return (
                <circle key={k} cx={x} cy={y} r={5} fill={sr.color} stroke="var(--surface)" strokeWidth={2}>
                  <title>{`${sr.label} · ${CORNER_NAME[CORNERS[k]]}: ${pct(v)}`}</title>
                </circle>
              );
            })}
          </g>
        );
      })}
      {labels && CORNERS.map((c, k) => {
        const [x, y] = point(k, 1.12);
        const v = one ? one.values[c] : undefined;
        const anchor = Math.abs(x - CX) < 2 ? "middle" : x < CX ? "end" : "start";
        const name = lines(CORNER_NAME[c]);
        const rows = name.length + (one ? 1 : 0);
        const top = k === 0 ? y - 17 * (rows - 1) - 6 : y > CY + R * 0.5 ? y + 14 : y - 4;
        return (
          <text key={c} x={x} y={top} textAnchor={anchor} className={s.label}>
            {name.map((n, i) => <tspan key={i} x={x} dy={i ? 17 : 0} className={s.name}>{n}</tspan>)}
            {one && <tspan x={x} dy={18} className={v == null ? s.none : s.value}>{v == null ? "chưa có dữ liệu" : pct(v)}</tspan>}
          </text>
        );
      })}
    </svg>
  );
}
