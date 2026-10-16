import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import s from "./ThemeToggle.module.css";

type Theme = "light" | "dark";
const KEY = "uniadvisor-theme";

function saved(): Theme | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
}

/** Light until the reader picks; the pick is remembered on this device only. */
export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(() => saved() ?? "light");
  useEffect(() => {
    if (saved()) document.documentElement.dataset.theme = theme;
  }, [theme]);
  function choose(t: Theme) {
    setTheme(t);
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem(KEY, t); } catch { /* storage blocked: the pick lasts for this page */ }
  }
  return [theme, choose];
}

export function ThemeToggle() {
  const [theme, choose] = useTheme();
  const dark = theme === "dark";
  return (
    <button type="button" className={s.toggle} onClick={() => choose(dark ? "light" : "dark")}
            aria-label={dark ? "Chuyển sang nền sáng" : "Chuyển sang nền tối"} title={dark ? "Nền sáng" : "Nền tối"}>
      <span className={[s.knob, dark ? s.dark : ""].join(" ")}>{dark ? <Moon size={16} /> : <Sun size={16} />}</span>
    </button>
  );
}
