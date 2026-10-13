import type { ReactNode } from "react";
import { Tooltip } from "./Tooltip";

type TermProps = {
  children: ReactNode;
  technical: string;
};

export function Term({ children, technical }: TermProps) {
  return (
    <Tooltip content={<span className="font-mono">{technical}</span>}>
      <span
        tabIndex={0}
        className="cursor-help rounded-sm underline decoration-dotted underline-offset-4"
      >
        {children}
      </span>
    </Tooltip>
  );
}
