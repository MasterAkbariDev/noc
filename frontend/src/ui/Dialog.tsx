import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode, type SyntheticEvent } from "react";
import { Button } from "./Button";

type DialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
};

export function Dialog({ open, onOpenChange, title, description, children }: DialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog === null) {
      return;
    }
    if (open && !dialog.open) {
      openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  function handleCancel(event: SyntheticEvent<HTMLDialogElement>) {
    event.preventDefault();
    onOpenChange(false);
  }

  function handleClose() {
    onOpenChange(false);
    openerRef.current?.focus();
    openerRef.current = null;
  }

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      aria-describedby={description === undefined ? undefined : descriptionId}
      onCancel={handleCancel}
      onClose={handleClose}
      className="m-auto w-[min(32rem,calc(100vw-2rem))] rounded-card border border-border bg-surface p-0 text-fg shadow-card backdrop:bg-black/50"
    >
      {open && (
        <div className="flex flex-col gap-4 p-5">
          <header className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h2 id={titleId} className="m-0 text-lg font-semibold">
                {title}
              </h2>
              {description !== undefined && (
                <p id={descriptionId} className="m-0 mt-1 text-sm text-muted">
                  {description}
                </p>
              )}
            </div>
            <Button variant="ghost" size="sm" aria-label="Close" onClick={() => onOpenChange(false)}>
              <X aria-hidden="true" size={16} />
            </Button>
          </header>
          {children}
        </div>
      )}
    </dialog>
  );
}
