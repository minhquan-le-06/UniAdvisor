import { AlertTriangle, ChevronDown, Info } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import s from "./NoticeBox.module.css";

export type Notice = {
  key: string;
  /** Bold lead-in, e.g. "Chưa đủ an toàn". */
  lead?: string;
  body: ReactNode;
  /** Smaller points under the bullet: notes that apply to the wishes in general. */
  details?: ReactNode[];
};

/** One kind of message (cảnh báo or lưu ý) as a frame with a bullet each and a button that folds it. */
export function NoticeBox({ tone, items, title, compact }: { tone: "warn" | "info"; items: Notice[]; title?: string; compact?: boolean }) {
  const [open, setOpen] = useState(true);
  const id = useId();
  if (!items.length) return null;
  const Icon = tone === "warn" ? AlertTriangle : Info;
  const name = title ?? (tone === "warn" ? "Cảnh báo" : "Lưu ý");
  return (
    <div className={[s.box, s[tone], compact ? s.compact : ""].join(" ")}>
      <Icon size={compact ? 18 : 22} aria-hidden className={s.icon} />
      <div className={s.text}>
        <button type="button" className={s.head} aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}>
          <strong className={s.title}>{name}{!open && ` (${items.length})`}</strong>
          <span className={s.toggle}>{open ? "Thu hẹp" : "Mở rộng"}<ChevronDown size={16} aria-hidden className={open ? s.up : undefined} /></span>
        </button>
        <ul id={id} className={s.list} hidden={!open}>
          {items.map((x) => (
            <li key={x.key}>
              <div>
                {x.lead && <strong>{x.lead}. </strong>}
                {x.body}
              </div>
              {x.details && x.details.length > 0 && (
                <ul className={s.details}>{x.details.map((d, i) => <li key={i}>{d}</li>)}</ul>
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
