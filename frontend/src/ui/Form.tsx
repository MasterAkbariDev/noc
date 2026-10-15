import { ChevronDown } from "lucide-react";
import type {
  FormHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import { cx } from "../lib/cx";

const CONTROL_CLASS =
  "w-full min-w-0 rounded-control border border-border bg-surface px-3 py-2 text-sm font-normal text-fg shadow-card transition-colors placeholder:text-muted hover:border-border-strong focus-visible:border-accent focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-50";

const COMPACT_CLASS = "py-1.5";

export type SelectOption = { value: string; label: string };

type FieldProps = {
  label: ReactNode;
  hint?: ReactNode;
  children: ReactNode;
  className?: string;
  compact?: boolean;
};

export function Field({ label, hint, children, className, compact = false }: FieldProps) {
  return (
    <label className={cx("grid min-w-0 gap-1.5 text-sm", compact ? "text-muted" : "font-medium text-fg", className)}>
      {label}
      {children}
      {hint !== undefined && <span className="text-xs font-normal text-muted">{hint}</span>}
    </label>
  );
}

export function FieldNote({ children }: { children: ReactNode }) {
  return <span className="font-normal text-muted">{children}</span>;
}

type TextInputProps = InputHTMLAttributes<HTMLInputElement> & { compact?: boolean };

export function TextInput({ className, compact = false, type = "text", ...rest }: TextInputProps) {
  return <input type={type} className={cx(CONTROL_CLASS, compact && COMPACT_CLASS, className)} {...rest} />;
}

export function TextArea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cx(CONTROL_CLASS, "resize-y", className)} {...rest} />;
}

type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & {
  options: SelectOption[];
  compact?: boolean;
};

export function Select({ options, className, compact = false, ...rest }: SelectProps) {
  return (
    <span className={cx("relative inline-grid min-w-0", className)}>
      <select className={cx(CONTROL_CLASS, compact && COMPACT_CLASS, "cursor-pointer appearance-none pr-9")} {...rest}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <ChevronDown
        aria-hidden="true"
        size={16}
        className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-muted"
      />
    </span>
  );
}

type CheckboxProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  label: ReactNode;
  hint?: ReactNode;
};

export function Checkbox({ label, hint, className, ...rest }: CheckboxProps) {
  return (
    <label className={cx("flex items-start gap-2.5 text-sm", className)}>
      <input type="checkbox" className="mt-0.5 size-4 shrink-0 cursor-pointer accent-accent" {...rest} />
      <span>
        {label}
        {hint !== undefined && <span className="text-xs text-muted"> ({hint})</span>}
      </span>
    </label>
  );
}

export function Fieldset({ legend, children }: { legend: string; children: ReactNode }) {
  return (
    <fieldset className="m-0 grid gap-2 border-0 p-0">
      <legend className="mb-1 text-sm font-medium">{legend}</legend>
      {children}
    </fieldset>
  );
}

type FormProps = FormHTMLAttributes<HTMLFormElement> & { width?: "full" | "narrow" };

export function Form({ className, width = "full", ...rest }: FormProps) {
  return <form className={cx("grid gap-4", width === "narrow" && "max-w-md", className)} {...rest} />;
}

export function FormMessage({ tone = "critical", children }: { tone?: "critical" | "ok"; children: ReactNode }) {
  return (
    <p role={tone === "critical" ? "alert" : "status"} className={cx("m-0 text-sm", tone === "critical" ? "text-critical" : "text-ok")}>
      {children}
    </p>
  );
}

export function FormActions({ align = "start", children }: { align?: "start" | "end"; children: ReactNode }) {
  return <div className={cx("flex flex-wrap gap-2", align === "end" && "justify-end")}>{children}</div>;
}

export function FilterBar({ children }: { children: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end gap-3 rounded-card border border-border bg-surface p-3 shadow-card">
      {children}
    </div>
  );
}
