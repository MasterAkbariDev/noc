import * as ToastPrimitive from "@radix-ui/react-toast";
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { cx } from "../lib/cx";

type ToastTone = "success" | "error";

type ToastItem = {
  id: number;
  tone: ToastTone;
  message: string;
};

export type ToastApi = {
  success: (message: string) => void;
  error: (message: string) => void;
};

const ToastContext = createContext<ToastApi | null>(null);

const TONE_CLASSES: Record<ToastTone, string> = {
  success: "border-ok bg-ok-soft text-fg",
  error: "border-critical bg-critical-soft text-fg",
};

export function Toaster({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const lastId = useRef(0);

  const show = useCallback((tone: ToastTone, message: string) => {
    lastId.current += 1;
    const id = lastId.current;
    setToasts((current) => [...current, { id, tone, message }]);
  }, []);

  const api = useMemo<ToastApi>(
    () => ({
      success: (message) => show("success", message),
      error: (message) => show("error", message),
    }),
    [show],
  );

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={api}>
      <ToastPrimitive.Provider swipeDirection="right" duration={5000}>
        {children}
        {toasts.map((toast) => (
          <ToastPrimitive.Root
            key={toast.id}
            type={toast.tone === "error" ? "foreground" : "background"}
            onOpenChange={(open) => {
              if (!open) {
                dismiss(toast.id);
              }
            }}
            className={cx(
              "flex items-start justify-between gap-3 rounded-card border p-3 shadow-card",
              TONE_CLASSES[toast.tone],
            )}
          >
            <ToastPrimitive.Description className="text-sm">{toast.message}</ToastPrimitive.Description>
            <ToastPrimitive.Close className="rounded-control px-2 text-sm text-muted hover:text-fg">
              Dismiss
            </ToastPrimitive.Close>
          </ToastPrimitive.Root>
        ))}
        <ToastPrimitive.Viewport className="fixed right-4 bottom-4 z-50 flex w-96 max-w-[calc(100vw-2rem)] flex-col gap-2 outline-none" />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (api === null) {
    throw new Error("useToast must be used inside Toaster");
  }
  return api;
}
