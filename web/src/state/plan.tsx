// The student's plan for this tab: the plan file kept in memory and in sessionStorage (so a reload keeps it; closing
// the tab forgets it), plus an undo stack of earlier plans. Nothing is sent anywhere except with an API call.
import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, type ReactNode } from "react";
import type { PlanJson } from "../api/types";

const KEY = "uniadvisor-plan";
const MAX_UNDO = 30;

export type State = {
  plan: PlanJson;
  undo: PlanJson[];
  /** The "Được / Đổi lại" lines of the chosen card (not part of the plan file). */
  words: { good: string[]; bad: string[] } | null;
};

type Action =
  | { type: "edit"; fn: (p: PlanJson) => PlanJson } // typing in the form: no undo step
  | { type: "commit"; plan: PlanJson }             // a change the student confirmed: one undo step
  | { type: "replace"; plan: PlanJson }            // a loaded file or a fresh start: clears undo
  | { type: "undo" }
  | { type: "words"; words: State["words"] };

export function reducer(s: State, a: Action): State {
  switch (a.type) {
    case "edit": return { ...s, plan: a.fn(s.plan) };
    case "commit": return { ...s, plan: a.plan, undo: [...s.undo, s.plan].slice(-MAX_UNDO) };
    case "replace": return { plan: a.plan, undo: [], words: null };
    case "undo": return s.undo.length ? { ...s, plan: s.undo[s.undo.length - 1], undo: s.undo.slice(0, -1) } : s;
    case "words": return { ...s, words: a.words };
  }
}

function load(): Pick<State, "plan" | "words"> | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    return data?.plan?.format === "uniadvisor-plan" ? { plan: data.plan, words: data.words ?? null } : null;
  } catch {
    return null;
  }
}

type Ctx = {
  plan: PlanJson;
  words: State["words"];
  canUndo: boolean;
  edit: (fn: (p: PlanJson) => PlanJson) => void;
  commit: (plan: PlanJson) => void;
  replace: (plan: PlanJson) => void;
  undo: () => void;
  setWords: (w: State["words"]) => void;
};

const PlanCtx = createContext<Ctx | null>(null);

/** `fresh` is the server's empty plan (GET /api/plan/new), used when this tab has none saved. */
export function PlanProvider({ fresh, children }: { fresh: PlanJson; children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, undefined, () => {
    const saved = load();
    return { plan: saved?.plan ?? fresh, undo: [], words: saved?.words ?? null };
  });

  useEffect(() => {
    try { sessionStorage.setItem(KEY, JSON.stringify({ plan: state.plan, words: state.words })); } catch { /* blocked */ }
  }, [state.plan, state.words]);

  // The edit runs inside the reducer on the latest plan, so rapid edits never overwrite each other.
  const edit = useCallback((fn: (p: PlanJson) => PlanJson) => dispatch({ type: "edit", fn }), []);

  const value = useMemo<Ctx>(() => ({
    plan: state.plan,
    words: state.words,
    canUndo: state.undo.length > 0,
    edit,
    commit: (plan) => dispatch({ type: "commit", plan }),
    replace: (plan) => dispatch({ type: "replace", plan }),
    undo: () => dispatch({ type: "undo" }),
    setWords: (words) => dispatch({ type: "words", words }),
  }), [state, edit]);

  return <PlanCtx.Provider value={value}>{children}</PlanCtx.Provider>;
}

export function usePlan(): Ctx {
  const c = useContext(PlanCtx);
  if (!c) throw new Error("usePlan outside PlanProvider");
  return c;
}

export function clearSavedPlan(): void {
  try { sessionStorage.removeItem(KEY); } catch { /* blocked */ }
}
