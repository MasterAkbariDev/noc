import { useId, useState } from "react";
import type { ActivityEntry } from "../../api/types";
import { Button, DataTable, RelativeTime, Term, type Column } from "../../ui";

const COLUMNS: Column<ActivityEntry>[] = [
  {
    key: "time",
    header: "When",
    cell: (entry) => <RelativeTime iso={entry.ts} className="whitespace-nowrap" />,
    className: "whitespace-nowrap",
  },
  {
    key: "actor",
    header: "Who",
    cell: (entry) => <span className="break-all">{entry.actor}</span>,
    className: "min-w-[8rem]",
  },
  {
    key: "action",
    header: "Action",
    cell: (entry) => <Term technical={entry.action}>{entry.action_label}</Term>,
    className: "min-w-[11rem]",
  },
  {
    key: "summary",
    header: "What happened",
    cell: (entry) => <ActivitySummary entry={entry} />,
    className: "min-w-[16rem] break-words",
  },
];

function ActivitySummary({ entry }: { entry: ActivityEntry }) {
  const [open, setOpen] = useState(false);
  const detailsId = useId();
  return (
    <div className="grid gap-2">
      <span>{entry.summary}</span>
      <Button
        variant="link"
        aria-expanded={open}
        aria-controls={open ? detailsId : undefined}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? "Hide details" : "Show details"}
      </Button>
      {open && (
        <pre
          id={detailsId}
          className="m-0 max-h-64 overflow-auto rounded-control border border-border bg-surface-2 p-2 text-xs break-all whitespace-pre-wrap"
        >
          {JSON.stringify(entry.payload, null, 2)}
        </pre>
      )}
    </div>
  );
}

type ActivityTableProps = {
  entries: ActivityEntry[];
  emptyText: string;
};

export function ActivityTable({ entries, emptyText }: ActivityTableProps) {
  return (
    <DataTable
      label="Activity"
      columns={COLUMNS}
      rows={entries}
      rowKey={(entry) => String(entry.id)}
      empty={emptyText}
    />
  );
}
