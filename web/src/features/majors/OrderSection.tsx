// "Xếp hướng học": up to two hướng học in order, each a main ngành (from the picks) and up to two close ngành, which
// the server proposes from the career data; the student can drop or replace them.
import { X } from "lucide-react";
import { useEffect, useRef } from "react";
import { api } from "../../api/client";
import { Combobox } from "../../components/Combobox";
import { QCard } from "../../components/QCard";
import { useData } from "../../state/boot";
import { usePlan } from "../../state/plan";
import { MAX_CLOSE, setClose, setItem } from "../../state/planOps";
import s from "../../pages/Input.module.css";

export function OrderSection() {
  const { plan, edit } = usePlan();
  const { labels, catalog } = useData();
  const picks = plan.majors.picks;
  const items = plan.majors.shortlist;
  const proposedFor = useRef<string[]>(items.map((e) => e.main));
  const nganh = catalog.filter((c) => c.level === "nganh");

  // A new main ngành gets the server's proposed close ngành (once per choice, so the student's edits stay).
  useEffect(() => {
    items.forEach((e, i) => {
      if (proposedFor.current[i] === e.main) return;
      proposedFor.current[i] = e.main;
      const exclude = items.map((x) => x.main);
      api.proposedClose(e.main, exclude)
        .then((close) => edit((p) => (p.majors.shortlist[i]?.main === e.main ? setClose(p, i, close.map((c) => c.code)) : p)))
        .catch(() => {});
    });
  }, [items, edit]);

  const pickOptions = picks.map((c) => ({ value: c, label: labels.get(c) ?? c }));

  return (
    <div className={s.section} id="huong-hoc">
      <h2 className={s.sectionTitle}><span className={s.num}>3</span> Xếp hướng học</h2>
      <QCard id="q-order" eyebrow="Thứ tự ưu tiên" title="Em chọn tối đa 2 hướng học, theo thứ tự em thích hơn"
             hint="Mỗi hướng học gồm một ngành chính và tối đa 2 ngành gần. Danh sách nguyện vọng ưu tiên hướng học 1."
             done={items.length > 0} eager={picks.length > 0}>
        {!picks.length && <p className="muted">Em chọn ít nhất một ngành ở phần trên trước nhé.</p>}
        {[0, 1].map((i) => {
          if (i === 1 && !items[0]) return null;
          const e = items[i];
          const options = pickOptions.filter((o) => !items.some((x, j) => j !== i && x.main === o.value));
          return (
            <div key={i} className={s.item}>
              <Combobox label={i === 0 ? "Hướng học 1" : "Hướng học 2 (không bắt buộc)"} options={options} value={e?.main ?? null}
                        clearable={i === 1} placeholder={i === 0 ? "Chọn" : "Không chọn"}
                        onChange={(v) => edit((p) => setItem(p, i, v))} />
              {e && (
                <div className={s.close}>
                  <span className="small" style={{ fontWeight: 600 }}>Ngành gần của {labels.get(e.main) ?? e.main} (tối đa {MAX_CLOSE})</span>
                  <div className={s.tray}>
                    {e.close.map((c) => (
                      <span key={c} className={s.trayChip}>
                        {labels.get(c) ?? c}
                        <button type="button" aria-label={`Bỏ ngành gần ${labels.get(c) ?? c}`}
                                onClick={() => edit((p) => setClose(p, i, e.close.filter((x) => x !== c)))}><X size={16} /></button>
                      </span>
                    ))}
                    {!e.close.length && <span className="small muted">Không có</span>}
                  </div>
                  {e.close.length < MAX_CLOSE && (
                    <Combobox label="Thêm ngành gần" placeholder="Chọn ngành" value={null}
                              options={nganh.filter((c) => c.code !== e.main && !e.close.includes(c.code)).map((c) => ({ value: c.code, label: c.label }))}
                              onChange={(v) => v && edit((p) => setClose(p, i, [...e.close, v]))} />
                  )}
                </div>
              )}
            </div>
          );
        })}
        <p className="xs muted">Ngành gần là ngành có công việc và kiến thức cần có giống ngành em chọn. Ứng dụng đề xuất sẵn tối đa 2 ngành gần (tính từ dữ liệu nghề nghiệp, đã rà soát); em có thể bỏ hoặc thay.</p>
      </QCard>
    </div>
  );
}
