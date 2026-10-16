import { RefreshCw } from "lucide-react";
import { Button } from "./Button";
import { Callout } from "./Callout";

/** A failed call with a way to try again (the plan is still in this tab). */
export function ErrorRetry({ text, onRetry }: { text: string; onRetry: () => void }) {
  return (
    <div className="page stack">
      <Callout tone="err" title="Chưa tải được">{text} Kế hoạch của em vẫn còn trong thẻ này.</Callout>
      <Button icon={<RefreshCw size={18} />} onClick={onRetry}>Thử lại</Button>
    </div>
  );
}
