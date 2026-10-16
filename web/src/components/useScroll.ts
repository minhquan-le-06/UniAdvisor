import { useEffect, useState } from "react";

/** True while the reader scrolls down past the top on a narrow screen: the header hides to give the page room, and
 * comes back on the first scroll up. Never hides with reduced motion or on wide screens. */
export function useHideOnScroll(threshold = 8): boolean {
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    let last = scrollY;
    let ticking = false;
    const narrow = matchMedia("(max-width: 719px)");
    const calm = matchMedia("(prefers-reduced-motion: reduce)");
    function update() {
      ticking = false;
      const y = scrollY;
      if (!narrow.matches || calm.matches || y < 80) setHidden(false);
      else if (y - last > threshold) setHidden(true);
      else if (last - y > threshold) setHidden(false);
      if (Math.abs(y - last) > threshold) last = y;
    }
    function onScroll() {
      if (!ticking) { ticking = true; requestAnimationFrame(update); }
    }
    addEventListener("scroll", onScroll, { passive: true });
    return () => removeEventListener("scroll", onScroll);
  }, [threshold]);
  return hidden;
}

/** True while the on-screen keyboard takes a good part of the screen (a phone, typing in a box). */
export function useKeyboardOpen(): boolean {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    const check = () => setOpen(vv.height < innerHeight * 0.75);
    vv.addEventListener("resize", check);
    return () => vv.removeEventListener("resize", check);
  }, []);
  return open;
}

/** The id of the section whose top was passed last (the part of a long page the reader is in). */
export function useActiveSection(ids: string[]): string {
  const [active, setActive] = useState(ids[0]);
  useEffect(() => {
    let ticking = false;
    function update() {
      ticking = false;
      let current = ids[0];
      for (const id of ids) {
        const el = document.getElementById(id);
        if (el && el.getBoundingClientRect().top < innerHeight * 0.35) current = id;
      }
      setActive(current);
    }
    function onScroll() {
      if (!ticking) { ticking = true; requestAnimationFrame(update); }
    }
    addEventListener("scroll", onScroll, { passive: true });
    update();
    return () => removeEventListener("scroll", onScroll);
  }, [ids.join(",")]);     // eslint-disable-line react-hooks/exhaustive-deps
  return active;
}
