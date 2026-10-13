import { TriangleAlert } from "lucide-react";
import { Button } from "./Button";

type ErrorStateProps = {
  title: string;
  message: string;
  onRetry?: () => void;
};

export function ErrorState({ title, message, onRetry }: ErrorStateProps) {
  return (
    <div role="alert" className="flex flex-col items-start gap-3 rounded-card border border-critical bg-critical-soft p-4">
      <p className="m-0 flex items-center gap-2 font-semibold text-critical">
        <TriangleAlert aria-hidden="true" size={18} />
        {title}
      </p>
      <p className="m-0 text-sm text-fg">{message}</p>
      {onRetry !== undefined && (
        <Button size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
