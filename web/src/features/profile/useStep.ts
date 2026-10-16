import { useCallback } from "react";
import { useSearchParams } from "react-router";

/** Which of the three input steps is open (?buoc=1..3, 1 when absent); moving to another goes back to the top. */
export function useStep(): [number, (n: number) => void] {
  const [sp, setSp] = useSearchParams();
  const n = Number(sp.get("buoc"));
  const step = n >= 1 && n <= 3 ? Math.round(n) : 1;
  const go = useCallback((k: number) => {
    setSp({ buoc: String(k) });
    scrollTo(0, 0);
  }, [setSp]);
  return [step, go];
}
