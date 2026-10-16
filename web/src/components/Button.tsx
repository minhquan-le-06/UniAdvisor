import type { ButtonHTMLAttributes, ReactNode } from "react";
import s from "./Button.module.css";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
  size?: "md" | "lg" | "sm";
  icon?: ReactNode;
  iconEnd?: ReactNode;
  block?: boolean;
};

/** A raised button that sinks when pressed. Primary is coral; secondary is outlined; ghost is text only. */
export function Button({ variant = "primary", size = "md", icon, iconEnd, block, className, children, type = "button", ...rest }: Props) {
  const cls = [s.btn, s[variant], s[size], block ? s.block : "", className ?? ""].join(" ");
  return (
    <button type={type} className={cls} {...rest}>
      {icon && <span className={s.icon} aria-hidden>{icon}</span>}
      {children && <span>{children}</span>}
      {iconEnd && <span className={s.icon} aria-hidden>{iconEnd}</span>}
    </button>
  );
}
