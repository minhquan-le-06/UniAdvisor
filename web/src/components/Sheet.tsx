import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import s from "./Sheet.module.css";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  /** "auto": a bottom sheet on phones, a panel on the right from 720 px. */
  side?: "auto" | "bottom" | "right";
  children: ReactNode;
  footer?: ReactNode;
};

/** A drawer or bottom sheet with a focus trap, Escape to close and a visible title. */
export function Sheet({ open, onOpenChange, title, description, side = "auto", children, footer }: Props) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className={s.overlay} />
        <Dialog.Content className={[s.content, s[side]].join(" ")}>
          <div className={s.grab} aria-hidden />
          <header className={s.head}>
            <div>
              <Dialog.Title className={s.title}>{title}</Dialog.Title>
              {description ? <Dialog.Description className={s.desc}>{description}</Dialog.Description>
                : <Dialog.Description className="sr-only">{title}</Dialog.Description>}
            </div>
            <Dialog.Close className={s.close} aria-label="Đóng"><X size={22} /></Dialog.Close>
          </header>
          <div className={s.body}>{children}</div>
          {footer && <footer className={s.foot}>{footer}</footer>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
