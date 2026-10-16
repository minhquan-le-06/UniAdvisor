import * as Popover from "@radix-ui/react-popover";
import { Download, FolderOpen, Menu, RotateCcw } from "lucide-react";
import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router";
import { api } from "../api/client";
import { usePlan } from "../state/plan";
import { forServer } from "../state/planOps";
import { useData } from "../state/boot";
import { PartsNav } from "../features/profile/PartsNav";
import { ThemeToggle } from "./ThemeToggle";
import { useHideOnScroll } from "./useScroll";
import { useToast } from "./Toast";
import s from "./AppShell.module.css";

const MAX_FILE = 1_000_000;

/** A slim header (logo, the parts of the input page, theme, plan menu) that slides away while scrolling down on a
 * phone, and the page below it. */
const TITLES: Record<string, string> = {
  "/": "UniAdvisor · Chọn ngành, xếp 15 nguyện vọng",
  "/bat-dau": "Về em và ngành em chọn · UniAdvisor",
  "/phuong-an": "Ba phương án gợi ý · UniAdvisor",
  "/danh-sach": "Danh sách nguyện vọng · UniAdvisor",
};

export function AppShell() {
  const hidden = useHideOnScroll();
  const { pathname } = useLocation();
  const onInput = pathname === "/bat-dau";
  const first = useRef(true);

  // A new page: its own title, back to the top, and focus on its heading for screen readers (not on first load).
  useEffect(() => {
    document.title = TITLES[pathname] ?? TITLES["/"];
    if (first.current) { first.current = false; return; }
    scrollTo(0, 0);
    const t = setTimeout(() => {
      const h = document.querySelector<HTMLElement>("main h1");
      if (h) { h.tabIndex = -1; h.focus({ preventScroll: true }); }
    }, 150);
    return () => clearTimeout(t);
  }, [pathname]);
  return (
    <>
      <a href="#main" className={s.skip}>Bỏ qua đến nội dung</a>
      <header className={[s.header, hidden ? s.hidden : ""].join(" ")}>
        <div className={s.inner}>
          <Link to="/" className={s.logo} aria-label="UniAdvisor, về trang đầu">
            <span className={s.logoFull}>UniAdvisor</span><span className={s.logoShort} aria-hidden>UA</span><span className={s.dot}>.</span>
          </Link>
          {onInput && <PartsNav />}
          <div className={s.tools}>
            <ThemeToggle />
            <RestartButton />
            <PlanMenu />
          </div>
        </div>
      </header>
      <main id="main" tabIndex={-1}><Outlet /></main>
    </>
  );
}

/** Clears everything entered and starts the input again. */
function RestartButton() {
  const { replace } = usePlan();
  const navigate = useNavigate();
  async function restart() {
    if (!confirm("Xoá mọi thông tin em đã nhập trong thẻ này và bắt đầu lại?")) return;
    replace(await api.newPlan());
    navigate("/bat-dau?buoc=1");
  }
  return (
    <button type="button" className={s.restart} onClick={restart} title="Xoá thông tin đã nhập và bắt đầu lại">
      <RotateCcw size={16} /> <span className={s.restartText}>Bắt đầu lại</span>
    </button>
  );
}

/** Save the plan as a file on the device, open a saved one, or start again. */
export function PlanMenu() {
  const { plan, replace } = usePlan();
  const { meta } = useData();
  const toast = useToast();
  const navigate = useNavigate();
  const file = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);

  function save() {
    const blob = new Blob([JSON.stringify(forServer(plan), null, 2) + "\n"], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "ke-hoach-uniadvisor.json";
    a.click();
    URL.revokeObjectURL(a.href);
    setOpen(false);
    toast("Đã tải kế hoạch về máy. Lần sau em chọn “Mở kế hoạch” để làm tiếp.", "ok");
  }

  async function load(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = "";
    setOpen(false);
    if (!f) return;
    if (f.size > MAX_FILE) { toast("Tệp quá lớn, không phải tệp kế hoạch của UniAdvisor.", "err"); return; }
    try {
      const raw = JSON.parse(await f.text());
      const { plan: loaded, warnings } = await api.normalizePlan(raw);
      replace(loaded);
      toast("Đã mở kế hoạch.", "ok");
      warnings.forEach((w) => toast(w, "warn"));
      navigate(loaded.lists.chosen ? "/danh-sach" : loaded.majors.shortlist.length ? "/phuong-an" : "/bat-dau");
    } catch (err) {
      toast(err instanceof SyntaxError ? "Không đọc được tệp. Hãy chọn tệp .json đã tải từ UniAdvisor." : (err as Error).message, "err");
    }
  }

  return (
    <>
      <input ref={file} type="file" accept="application/json,.json" hidden onChange={load} aria-hidden tabIndex={-1} />
      <Popover.Root open={open} onOpenChange={setOpen}>
        <Popover.Trigger className={s.menuBtn} aria-label="Kế hoạch của em">
          <Menu size={22} />
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Content className={s.menu} align="end" sideOffset={8}>
            <button type="button" className={s.item} onClick={save}><Download size={18} /> Lưu kế hoạch về máy</button>
            <button type="button" className={s.item} onClick={() => file.current?.click()}><FolderOpen size={18} /> Mở kế hoạch đã lưu</button>
            <p className={s.note}>Kế hoạch năm {meta.admission_year}. Ứng dụng không lưu bản nào trên máy chủ.</p>
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
    </>
  );
}

/** Opens the file picker of the plan menu from elsewhere (the landing page). */
export function useOpenPlanFile() {
  return () => document.querySelector<HTMLInputElement>('input[type="file"][accept^="application/json"]')?.click();
}
