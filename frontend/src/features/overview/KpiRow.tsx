import type { Kpis } from "../../api/types";
import { KpiTile } from "../../ui";
import { kpiViews } from "./model";

type KpiRowProps = {
  kpis: Kpis;
  llmMode?: string;
};

export function KpiRow({ kpis, llmMode }: KpiRowProps) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {kpiViews(kpis, llmMode).map((view) => (
        <KpiTile
          key={view.key}
          label={view.label}
          value={view.value}
          hint={view.hint}
          tone={view.tone}
          to={view.to}
        />
      ))}
    </div>
  );
}
