import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { WishExplanation } from "../../api/types";
import { Button } from "../../components/Button";
import { Callout } from "../../components/Callout";
import { Sheet } from "../../components/Sheet";
import { usePlan } from "../../state/plan";
import { forServer } from "../../state/planOps";
import s from "./Chosen.module.css";

/** "Vì sao NVn ở đây?": the fixed explanation of one wish (explanations.py), part by part. */
export function ExplainSheet({ nv, onClose }: { nv: number | null; onClose: () => void }) {
  const { plan } = usePlan();
  const [e, setE] = useState<WishExplanation | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (nv == null) return;
    setE(null); setError(null);
    let off = false;
    api.explain(forServer(plan), nv).then((x) => { if (!off) setE(x); }).catch((x) => { if (!off) setError(x.message); });
    return () => { off = true; };
  }, [nv]);      // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Sheet open={nv != null} onOpenChange={(o) => { if (!o) onClose(); }} title={`Vì sao NV${nv ?? ""} ở đây?`}
           description={e?.title} footer={<Button block onClick={onClose}>Đã hiểu</Button>}>
      {error && <Callout tone="err">{error}</Callout>}
      {!e && !error && <div className={s.loadingLines} aria-busy="true"><span /><span /><span /></div>}
      {e && (
        <div className="stack">
          <Callout tone="info" title={cap(e.level)}>{e.verdict}</Callout>
          <ul className={s.numbers}>{e.numbers.map((n) => <li key={n}>{n}</li>)}</ul>
          <section><h4 className={s.h4}>Vì sao có trong danh sách</h4><p>{e.why_in_list}</p></section>
          <section><h4 className={s.h4}>Vì sao ở vị trí này</h4><p>{e.placement}</p></section>
          {e.notices.length > 0 && (
            <section><h4 className={s.h4}>Lưu ý</h4><ul className={s.notices}>{e.notices.map((n) => <li key={n}>{n}</li>)}</ul></section>
          )}
        </div>
      )}
    </Sheet>
  );
}

const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);
