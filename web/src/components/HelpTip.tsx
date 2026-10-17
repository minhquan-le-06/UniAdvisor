import * as Popover from "@radix-ui/react-popover";
import { CircleHelp } from "lucide-react";
import type { ReactNode } from "react";
import s from "./HelpTip.module.css";

/** A "?" button that opens a short explanation; works with the keyboard and a tap, and closes with Escape. */
export function HelpTip({ label, title, children }: { label: string; title: string; children: ReactNode }) {
  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button type="button" className={s.trigger} aria-label={label}><CircleHelp size={20} aria-hidden /></button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className={s.content} sideOffset={8} collisionPadding={16}>
          <strong className={s.title}>{title}</strong>
          <div className="small">{children}</div>
          <Popover.Arrow className={s.arrow} />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
