import { CircleHelp, Info, OctagonAlert, TriangleAlert, type LucideIcon } from "lucide-react";
import { severityView, type Tone } from "../lib/tones";
import { Badge } from "./Badge";

const TONE_ICONS: Partial<Record<Tone, LucideIcon>> = {
  critical: OctagonAlert,
  warning: TriangleAlert,
  info: Info,
  neutral: CircleHelp,
};

export function SeverityBadge({ severity }: { severity: string }) {
  const view = severityView(severity);
  return (
    <Badge tone={view.tone} icon={TONE_ICONS[view.tone]}>
      {view.label}
    </Badge>
  );
}
