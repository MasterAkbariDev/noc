import type { LucideIcon } from "lucide-react";
import type { ButtonHTMLAttributes } from "react";
import { cx } from "../lib/cx";

export type IconButtonVariant = "ghost" | "secondary" | "nav";

const VARIANT_CLASSES: Record<IconButtonVariant, string> = {
  ghost: "border-transparent text-muted hover:bg-surface-2 hover:text-fg",
  secondary: "border-border bg-surface text-fg shadow-card hover:bg-surface-2",
  nav: "border-transparent text-nav-muted hover:bg-nav-hover hover:text-nav-fg",
};

type IconButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & {
  label: string;
  icon: LucideIcon;
  variant?: IconButtonVariant;
  showLabel?: boolean;
};

export function IconButton({ label, icon: Icon, variant = "ghost", showLabel = false, className, type = "button", ...rest }: IconButtonProps) {
  return (
    <button
      type={type}
      aria-label={showLabel ? undefined : label}
      className={cx(
        "inline-flex items-center gap-2 rounded-control border text-sm font-medium transition-colors",
        showLabel ? "px-2.5 py-1.5" : "p-1.5",
        VARIANT_CLASSES[variant],
        className,
      )}
      {...rest}
    >
      <Icon aria-hidden="true" size={16} />
      {showLabel && label}
    </button>
  );
}
