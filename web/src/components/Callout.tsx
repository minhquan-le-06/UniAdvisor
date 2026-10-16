import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import type { ReactNode } from "react";
import s from "./Callout.module.css";

const ICON = { info: Info, ok: CheckCircle2, warn: AlertTriangle, err: XCircle };
const NAME = { info: "Lưu ý", ok: "Xong", warn: "Cảnh báo", err: "Lỗi" };

/** A message box: an icon and a hidden word say its kind, so colour is never the only signal. */
export function Callout({ tone = "info", title, children }: { tone?: keyof typeof ICON; title?: string; children: ReactNode }) {
  const Icon = ICON[tone];
  return (
    <div className={[s.callout, s[tone]].join(" ")} role={tone === "err" ? "alert" : undefined}>
      <Icon size={22} aria-hidden className={s.icon} />
      <div className={s.text}>
        <span className="sr-only">{NAME[tone]}: </span>
        {title && <strong className={s.title}>{title}</strong>}
        <div>{children}</div>
      </div>
    </div>
  );
}
