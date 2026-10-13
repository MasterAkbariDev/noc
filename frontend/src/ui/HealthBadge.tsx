import { CircleCheck, CircleDashed, CircleX, TriangleAlert, type LucideIcon } from "lucide-react";
import { healthView, type HealthStatus } from "../lib/tones";
import { Badge } from "./Badge";

const STATUS_ICONS: Record<HealthStatus, LucideIcon> = {
  ok: CircleCheck,
  degraded: TriangleAlert,
  down: CircleX,
  unknown: CircleDashed,
};

export function HealthBadge({ status }: { status: HealthStatus }) {
  const view = healthView(status);
  return (
    <Badge tone={view.tone} icon={STATUS_ICONS[status]}>
      {view.label}
    </Badge>
  );
}
