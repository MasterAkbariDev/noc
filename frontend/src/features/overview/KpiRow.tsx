import type { Kpis } from "../../api/types";
import { KpiTile } from "../../ui";
import { kpiViews } from "./model";

export function KpiRow({ kpis }: { kpis: Kpis }) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {kpiViews(kpis).map((view) => (
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
