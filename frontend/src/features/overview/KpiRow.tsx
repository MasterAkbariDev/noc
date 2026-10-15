import type { Kpis } from "../../api/types";
import { KpiTile } from "../../ui";
import { kpiViews, type KpiTrends } from "./model";

type KpiRowProps = {
  kpis: Kpis;
  llmMode?: string;
  trends?: KpiTrends;
};

export function KpiRow({ kpis, llmMode, trends }: KpiRowProps) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {kpiViews(kpis, llmMode, trends).map((view) => (
        <KpiTile
          key={view.key}
          label={view.label}
          value={view.value}
          hint={view.hint}
          tone={view.tone}
          to={view.to}
          icon={view.icon}
          trend={view.trend}
        />
      ))}
    </div>
  );
}
