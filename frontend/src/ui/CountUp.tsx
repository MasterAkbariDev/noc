import { useEffect, useRef, useState } from "react";

const DURATION_MS = 600;

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia !== "function" || window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function easeOut(progress: number): number {
  return 1 - (1 - progress) ** 3;
}

export function CountUp({ value, className }: { value: number; className?: string }) {
  const [shown, setShown] = useState(value);
  const shownRef = useRef(value);

  useEffect(() => {
    const from = shownRef.current;
    if (from === value || prefersReducedMotion()) {
      shownRef.current = value;
      setShown(value);
      return;
    }
    let frame = 0;
    const started = performance.now();
    function step(now: number) {
      const progress = Math.min(1, (now - started) / DURATION_MS);
      const next = Math.round(from + (value - from) * easeOut(progress));
      shownRef.current = next;
      setShown(next);
      if (progress < 1) {
        frame = requestAnimationFrame(step);
      }
    }
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [value]);

  return <span className={className}>{shown}</span>;
}
