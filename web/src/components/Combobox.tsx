import * as Popover from "@radix-ui/react-popover";
import { Command } from "cmdk";
import { Check, ChevronDown, X } from "lucide-react";
import { useId, useState } from "react";
import s from "./Combobox.module.css";

export type ComboOption = { value: string; label: string; hint?: string };

type Props = {
  label: string;
  options: ComboOption[];
  value: string | null;
  onChange: (v: string | null) => void;
  placeholder?: string;
  searchPlaceholder?: string;
  clearable?: boolean;
  hint?: string;
};

/** Search without accents: "ha noi" finds "Hà Nội", "dh bach khoa" finds "Đại học Bách khoa". */
export function fold(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();
}

function match(value: string, search: string, keywords?: string[]): number {
  const hay = fold([value, ...(keywords ?? [])].join(" "));
  const words = fold(search).split(/\s+/).filter(Boolean);
  if (!words.length) return 1;
  if (!words.every((w) => hay.includes(w))) return 0;
  return hay.startsWith(words[0]) ? 1 : 0.5;
}

/** A select with a search box (long lists: provinces, schools, ngành). */
export function Combobox({ label, options, value, onChange, placeholder = "Chọn", searchPlaceholder = "Gõ để tìm...", clearable, hint }: Props) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const current = options.find((o) => o.value === value) ?? null;

  return (
    <div className={s.field}>
      <span id={`${id}-label`} className={s.label}>{label}</span>
      <Popover.Root open={open} onOpenChange={setOpen}>
        <div className={s.triggerRow}>
          <Popover.Trigger asChild>
            <button type="button" className={s.trigger} aria-labelledby={`${id}-label ${id}-value`}>
              <span id={`${id}-value`} className={current ? s.value : s.placeholder}>{current?.label ?? placeholder}</span>
              <ChevronDown size={20} aria-hidden className={s.chev} />
            </button>
          </Popover.Trigger>
          {clearable && current && (
            <button type="button" className={s.clear} onClick={() => onChange(null)} aria-label={`Bỏ chọn ${label}`}>
              <X size={18} />
            </button>
          )}
        </div>
        <Popover.Portal>
          <Popover.Content className={s.content} sideOffset={6} align="start">
            <Command filter={match} label={label}>
              <Command.Input className={s.search} placeholder={searchPlaceholder} autoFocus />
              <Command.List className={s.list}>
                <Command.Empty className={s.empty}>Không tìm thấy. Em thử cách viết khác nhé.</Command.Empty>
                {options.map((o) => (
                  <Command.Item
                    key={o.value}
                    value={o.label}
                    keywords={[o.value, o.hint ?? ""]}
                    className={s.item}
                    onSelect={() => { onChange(o.value); setOpen(false); }}
                  >
                    <span className={s.itemText}>
                      {o.label}
                      {o.hint && <span className={s.itemHint}>{o.hint}</span>}
                    </span>
                    {o.value === value && <Check size={18} aria-hidden />}
                  </Command.Item>
                ))}
              </Command.List>
            </Command>
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
      {hint && <span className={s.hint}>{hint}</span>}
    </div>
  );
}
