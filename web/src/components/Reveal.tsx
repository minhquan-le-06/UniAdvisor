import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import s from "./Reveal.module.css";

type Props = {
  children: ReactNode;
  /** Shown at once (the first few cards), without waiting to be scrolled to. */
  eager?: boolean;
  /** Position in a group: each next one starts 60 ms later. */
  index?: number;
  className?: string;
  id?: string;
  /** data-* attributes for the wrapper (the progress rail of the input page reads them). */
  data?: Record<string, string | undefined>;
};

/** Slides a block in when it scrolls into view, once. Without IntersectionObserver (old browsers, tests) or with
 * reduced motion the block is simply shown. */
export function Reveal({ children, eager, index = 0, className, id, data }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(() => !!eager || typeof IntersectionObserver === "undefined");

  useEffect(() => {
    if (shown || !ref.current) return;
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) { setShown(true); io.disconnect(); }
    }, { rootMargin: "0px 0px -10% 0px", threshold: 0.08 });
    io.observe(ref.current);
    return () => io.disconnect();
  }, [shown]);

  return (
    <div ref={ref} id={id} {...Object.fromEntries(Object.entries(data ?? {}).map(([k, v]) => [`data-${k}`, v]))} className={[s.reveal, shown ? s.shown : "", className ?? ""].join(" ")}
         style={{ "--delay": `${Math.min(index, 8) * 60}ms` } as CSSProperties}>
      {children}
    </div>
  );
}
