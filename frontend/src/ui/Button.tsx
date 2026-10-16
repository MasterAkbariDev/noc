import type { ButtonHTMLAttributes } from "react";
import { Link, type LinkProps } from "react-router";
import { cx } from "../lib/cx";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "link";
export type ButtonSize = "sm" | "md";

type ButtonOptions = { variant?: ButtonVariant; size?: ButtonSize };

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & ButtonOptions;

type ButtonLinkProps = LinkProps & ButtonOptions;

const BASE_CLASS =
  "inline-flex items-center justify-center justify-self-start gap-2 rounded-control border font-medium whitespace-nowrap transition-[color,background-color,border-color,transform] duration-150 disabled:cursor-not-allowed disabled:opacity-50";

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: "border-accent bg-accent text-accent-fg hover:brightness-110 active:scale-[0.98]",
  secondary: "border-border bg-surface text-fg hover:border-border-strong hover:bg-surface-2 active:scale-[0.98]",
  ghost: "border-transparent bg-transparent text-fg hover:bg-surface-2",
  danger: "border-critical bg-critical text-critical-fg shadow-card hover:brightness-110",
  link: "w-fit border-transparent bg-transparent p-0 text-accent underline underline-offset-4 hover:brightness-125",
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: "px-2.5 py-1 text-sm",
  md: "px-3.5 py-2 text-sm",
};

export function buttonClass({ variant = "secondary", size = "md" }: ButtonOptions = {}): string {
  return cx(BASE_CLASS, VARIANT_CLASSES[variant], variant !== "link" && SIZE_CLASSES[size], variant === "link" && "text-sm");
}

export function Button({ variant, size, type = "button", className, ...rest }: ButtonProps) {
  return <button type={type} className={cx(buttonClass({ variant, size }), className)} {...rest} />;
}

export function ButtonLink({ variant, size, className, ...rest }: ButtonLinkProps) {
  return <Link className={cx(buttonClass({ variant, size }), typeof className === "string" ? className : undefined)} {...rest} />;
}
