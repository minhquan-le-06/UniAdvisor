import * as T from "@radix-ui/react-toast";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import s from "./Toast.module.css";

type Tone = "info" | "ok" | "warn" | "err";
type Item = { id: number; tone: Tone; text: string };
const ICON = { info: Info, ok: CheckCircle2, warn: AlertTriangle, err: XCircle };

const Ctx = createContext<(text: string, tone?: Tone) => void>(() => {});

/** Short messages at the bottom ("Đã lưu", errors from the server). Read out politely by screen readers. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Item[]>([]);
  const push = useCallback((text: string, tone: Tone = "info") => {
    setItems((xs) => [...xs.slice(-2), { id: Date.now() + Math.random(), tone, text }]);
  }, []);
  return (
    <Ctx.Provider value={push}>
      <T.Provider swipeDirection="down" duration={5000}>
        {children}
        {items.map((it) => {
          const Icon = ICON[it.tone];
          return (
            <T.Root key={it.id} className={[s.toast, s[it.tone]].join(" ")}
                    type={it.tone === "err" ? "foreground" : "background"}
                    onOpenChange={(open) => { if (!open) setItems((xs) => xs.filter((x) => x.id !== it.id)); }}>
              <Icon size={20} aria-hidden />
              <T.Description className={s.text}>{it.text}</T.Description>
              <T.Close className={s.close} aria-label="Đóng"><X size={18} /></T.Close>
            </T.Root>
          );
        })}
        <T.Viewport className={s.viewport} label="Thông báo ({hotkey})" />
      </T.Provider>
    </Ctx.Provider>
  );
}

export function useToast() {
  return useContext(Ctx);
}
