import * as A from "@radix-ui/react-accordion";
import { ChevronDown } from "lucide-react";
import type { ReactNode } from "react";
import s from "./Accordion.module.css";

/** One collapsible section ("Xem chi tiết", "Danh sách được lập thế nào?"). */
export function Disclosure({ title, children, defaultOpen = false }: { title: ReactNode; children: ReactNode; defaultOpen?: boolean }) {
  return (
    <A.Root type="single" collapsible defaultValue={defaultOpen ? "x" : undefined} className={s.root}>
      <A.Item value="x" className={s.item}>
        <A.Header asChild><div className={s.header}>
          <A.Trigger className={s.trigger}>
            <span>{title}</span>
            <ChevronDown size={20} aria-hidden className={s.chev} />
          </A.Trigger>
        </div></A.Header>
        <A.Content className={s.content}>
          <div className={s.inner}>{children}</div>
        </A.Content>
      </A.Item>
    </A.Root>
  );
}
