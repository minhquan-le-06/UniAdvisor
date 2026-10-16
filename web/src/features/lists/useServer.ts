import { useEffect, useState } from "react";
import type { PlanJson } from "../../api/types";
import { forServer } from "../../state/planOps";

/** Ask the server about the current plan; again whenever the plan changes (the older answer is dropped). */
export function useServer<T>(plan: PlanJson, call: (p: PlanJson, signal: AbortSignal) => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const key = JSON.stringify(forServer(plan));

  useEffect(() => {
    const ctl = new AbortController();
    setLoading(true);
    call(JSON.parse(key), ctl.signal)
      .then((d) => { setData(d); setError(null); })
      .catch((e) => { if (e.name !== "AbortError") setError(e.message); })
      .finally(() => { if (!ctl.signal.aborted) setLoading(false); });
    return () => ctl.abort();
  }, [key, attempt]);   // eslint-disable-line react-hooks/exhaustive-deps

  return { data, error, loading, retry: () => setAttempt((x) => x + 1) };
}
