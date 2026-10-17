import { useCallback, useState } from "react";
import { api } from "../../api/client";
import type { Chosen } from "../../api/types";
import { useToast } from "../../components/Toast";
import { useData } from "../../state/boot";
import { usePlan } from "../../state/plan";
import { forServer } from "../../state/planOps";
import { buildPlanPrintHtml, writePrintLoading } from "./planPrint";

/** Opens a printer-friendly plan in a separate tab. Keeping this outside the JSON download prevents the two formats
 * from being confused: only the JSON file can be uploaded to restore a plan. */
export function usePrintPlan() {
  const { plan } = usePlan();
  const { meta, labels } = useData();
  const toast = useToast();
  const [printing, setPrinting] = useState(false);

  const printPlan = useCallback(async () => {
    if (printing) return;
    // Open before awaiting the API: this preserves the user gesture that browser popup blockers require.
    const popup = window.open("", "_blank");
    if (!popup) {
      toast("Trình duyệt đã chặn cửa sổ in. Em hãy cho phép cửa sổ bật lên rồi thử lại nhé.", "err");
      return;
    }
    const snapshot = forServer(plan);
    writePrintLoading(popup);
    setPrinting(true);
    let chosen: Chosen | null = null;
    let problem: string | null = null;
    try {
      if (snapshot.lists.chosen) {
        const response = await api.chosen(snapshot);
        if ("header" in response) chosen = response;
        else problem = "Không đủ thông tin để lập lại danh sách nguyện vọng ở thời điểm in.";
      }
    } catch {
      problem = "Không tải được danh sách nguyện vọng mới nhất. Bản in vẫn gồm thông tin kế hoạch em đã nhập.";
    } finally {
      setPrinting(false);
    }
    if (popup.closed) return;
    popup.document.open();
    popup.document.write(buildPlanPrintHtml({ plan: snapshot, meta, labels, chosen, problem }));
    popup.document.close();
    // Give the new document one paint before opening the native dialog; its title becomes the suggested PDF name.
    window.setTimeout(() => { if (!popup.closed) { popup.focus(); popup.print(); } }, 200);
    toast("Cửa sổ in đã mở. Chọn “Lưu dưới dạng PDF” để tải bản in.", "ok");
  }, [labels, meta, plan, printing, toast]);

  return { printPlan, printing };
}
