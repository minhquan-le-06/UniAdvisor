// A small rail beside the open step: one row per question card (ticked when answered), the one being read highlighted,
// and a count on top. It reads the cards from the page (QCard marks itself with data-q / data-done), so the 12 quiz
// questions and the other cards are listed without each section having to say what it holds.
import { useEffect, useState } from "react";
import { useActiveSection } from "../../components/useScroll";
import s from "./StepRail.module.css";

type Item = { id: string; label: string; done: boolean };

const same = (a: Item[], b: Item[]) =>
  a.length === b.length && a.every((x, i) => x.id === b[i].id && x.label === b[i].label && x.done === b[i].done);

export function StepRail({ rootId, step }: { rootId: string; step: number }) {
  const [items, setItems] = useState<Item[]>([]);

  useEffect(() => {
    const root = document.getElementById(rootId);
    if (!root) return;
    const scan = () => {
      const next = [...root.querySelectorAll<HTMLElement>("[data-q]")]
        .map((el) => ({ id: el.id, label: el.dataset.q ?? "", done: el.dataset.done === "1" }));
      setItems((prev) => (same(prev, next) ? prev : next));
    };
    scan();
    const mo = new MutationObserver(scan);
    mo.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ["data-done", "data-q"] });
    return () => mo.disconnect();
  }, [rootId, step]);

  const active = useActiveSection(items.map((i) => i.id));
  if (!items.length) return null;
  const done = items.filter((i) => i.done).length;

  return (
    <nav className={s.rail} aria-label="Tiến độ các câu hỏi">
      <p className={s.count}><strong>{done}</strong> / {items.length} câu đã trả lời</p>
      <div className={s.bar} aria-hidden><span style={{ width: `${(done / items.length) * 100}%` }} /></div>
      <ol className={s.list}>
        {items.map((it, i) => (
          <li key={it.id}>
            <a href={`#${it.id}`} title={it.label} aria-current={active === it.id ? "true" : undefined}
               className={[s.row, it.done ? s.done : "", active === it.id ? s.active : ""].join(" ")}
               onClick={(e) => { e.preventDefault(); document.getElementById(it.id)?.scrollIntoView({ behavior: "smooth", block: "center" }); }}>
              <span className={s.dot}>{it.done ? "✓" : i + 1}</span>
              <span className={s.text}>{it.label}</span>
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}
