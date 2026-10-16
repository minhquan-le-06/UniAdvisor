import { useCallback, useState } from "react";
import { api } from "../../api/client";
import type { ApplyResult } from "../../api/types";
import { useToast } from "../../components/Toast";
import { usePlan } from "../../state/plan";
import { forServer } from "../../state/planOps";

export type ChangeItemJson = { kind: string; params?: Record<string, unknown>; open?: string[]; text?: string };

/** Apply confirmed changes on the server; the new plan becomes one undo step. Returns the server's answer (what was
 * done, errors, how the list changed) for the caller to show; errors of the call itself become a toast. */
export function useApply() {
  const { plan, commit } = usePlan();
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  const apply = useCallback(async (items: ChangeItemJson[], quiet = false): Promise<ApplyResult | null> => {
    setBusy(true);
    try {
      const res = await api.apply(forServer(plan), items);
      if (res.changed) commit(res.plan);
      if (!quiet) {
        if (res.done.length) toast(`Đã áp dụng: ${res.done.join("; ")}.`, "ok");
        res.errors.forEach((e) => toast(e, "err"));
      }
      return res;
    } catch (e) {
      toast((e as Error).message, "err");
      return null;
    } finally {
      setBusy(false);
    }
  }, [plan, commit, toast]);

  return { apply, busy };
}
