// The chat: a floating button opens it. A message is split and read by fixed rules on the server (no language
// model); questions are answered at once, changes come back on a card the student checks and confirms. The chat never
// edits the list itself, and messages are kept only in this page.
import { MessageCircle, Send } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "../../api/client";
import type { ChangeItem } from "../../api/types";
import { RichText } from "../../components/RichText";
import { Sheet } from "../../components/Sheet";
import { useToast } from "../../components/Toast";
import { usePlan } from "../../state/plan";
import { forServer } from "../../state/planOps";
import { ChangeCard } from "./ChangeCard";
import s from "./Chat.module.css";

export type ChatMsg = { id: number; role: "user" | "bot"; text: string } | { id: number; role: "card"; items: ChangeItem[]; done: boolean };

const EXAMPLES = ["Toán em được 8,5", "Bỏ trường Bách khoa Hà Nội", "Vì sao NV3 ở đó?", "Ngân sách 30 triệu", "Học phí NV1 bao nhiêu?"];
let seq = 0;

export function Chat({ log, setLog }: { log: ChatMsg[]; setLog: (f: (l: ChatMsg[]) => ChatMsg[]) => void }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const { plan } = usePlan();
  const toast = useToast();
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [log, open]);

  async function send(msg: string) {
    const m = msg.trim();
    if (!m || busy) return;
    setText("");
    setLog((l) => [...l, { id: ++seq, role: "user", text: m }]);
    setBusy(true);
    try {
      const r = await api.chat(forServer(plan), m.slice(0, 1000));
      setLog((l) => {
        const next = [...l, ...r.answers.map((a) => ({ id: ++seq, role: "bot" as const, text: a }))];
        if (r.help) next.push({ id: ++seq, role: "bot", text: r.help });
        if (r.items.length) {
          next.push({ id: ++seq, role: "bot", text: "Mình hiểu em muốn thay đổi những điều dưới đây. Em kiểm tra rồi bấm **Xác nhận** nhé." });
          next.push({ id: ++seq, role: "card", items: r.items, done: false });
        }
        return next;
      });
    } catch (e) {
      toast((e as Error).message, "err");
    } finally {
      setBusy(false);
    }
  }

  function submit(e: FormEvent) { e.preventDefault(); send(text); }

  function closeCard(id: number, reply: string) {
    setLog((l) => [...l.map((m) => (m.id === id && m.role === "card" ? { ...m, done: true } : m)), { id: ++seq, role: "bot", text: reply }]);
  }

  return (
    <>
      <button type="button" className={s.fab} onClick={() => setOpen(true)} aria-label="Mở chat để hỏi hoặc chỉnh danh sách">
        <MessageCircle size={24} />
        {log.length === 0 && <span className={s.fabHint}>Hỏi mình</span>}
      </button>
      <Sheet open={open} onOpenChange={setOpen} title="Hỏi hoặc chỉnh danh sách"
             description="Chat chỉ đổi thông tin em đã nhập (rồi danh sách được lập lại) hoặc trả lời từ dữ liệu của ứng dụng. Mọi thay đổi đều cần em bấm Xác nhận."
             footer={
               <form className={s.form} onSubmit={submit}>
                 <input className={s.input} value={text} onChange={(e) => setText(e.target.value)} maxLength={1000}
                        placeholder="Nhắn yêu cầu hoặc câu hỏi..." aria-label="Tin nhắn" />
                 <button type="submit" className={s.send} disabled={!text.trim() || busy} aria-label="Gửi"><Send size={20} /></button>
               </form>
             }>
        <div className={s.log} aria-live="polite">
          {log.length === 0 && (
            <div className={s.empty}>
              <p className="small muted">Ví dụ:</p>
              <div className={s.examples}>
                {EXAMPLES.map((x) => <button key={x} type="button" className={s.example} onClick={() => send(x)}>{x}</button>)}
              </div>
            </div>
          )}
          {log.map((m) =>
            m.role === "card" ? (
              <ChangeCard key={m.id} items={m.items} done={m.done} onClose={(reply) => closeCard(m.id, reply)} />
            ) : (
              <div key={m.id} className={m.role === "user" ? s.user : s.bot}><RichText text={m.text} /></div>
            ))}
          {busy && <div className={s.bot}><span className={s.typing} aria-label="Đang trả lời"><i /><i /><i /></span></div>}
          <div ref={end} />
        </div>
      </Sheet>
    </>
  );
}
