import type { ButtonHTMLAttributes } from "react";
import { cx } from "../lib/cx";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

type ButtonOptions = { variant?: ButtonVariant; size?: ButtonSize };

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & ButtonOptions;

const BASE_CLASS =
  "inline-flex items-center justify-center justify-self-start gap-2 rounded-control border font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50";

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: "border-accent bg-accent text-accent-fg hover:brightness-110",
  secondary: "border-border bg-surface text-fg hover:bg-surface-2",
  ghost: "border-transparent bg-transparent text-fg hover:bg-surface-2",
  danger: "border-critical bg-critical text-critical-fg hover:brightness-110",
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: "px-2.5 py-1 text-sm",
  md: "px-3.5 py-2 text-sm",
};

export function buttonClass({ variant = "secondary", size = "md" }: ButtonOptions = {}): string {
  return cx(BASE_CLASS, VARIANT_CLASSES[variant], SIZE_CLASSES[size]);
}

export function Button({ variant, size, type = "button", className, ...rest }: ButtonProps) {
  return <button type={type} className={cx(buttonClass({ variant, size }), className)} {...rest} />;
}
