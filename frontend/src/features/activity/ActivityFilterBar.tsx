import { useState, type FormEvent } from "react";
import { buttonClass, Button } from "../../ui";
import { ACTIVITY_ACTIONS, ACTOR_MAX_LENGTH, NO_FILTERS, type ActivityFilters } from "./filters";

type ActivityFilterBarProps = {
  filters: ActivityFilters;
  onChange: (next: ActivityFilters) => void;
};

export function ActivityFilterBar({ filters, onChange }: ActivityFilterBarProps) {
  const [actorDraft, setActorDraft] = useState(filters.actor);
  const filtered = filters.action !== "" || filters.actor !== "";

  function submitActor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onChange({ ...filters, actor: actorDraft.trim() });
  }

  return (
    <div className="mb-4 flex flex-wrap items-end gap-3">
      <label className="grid gap-1 text-sm text-muted">
        Action
        <select
          value={filters.action}
          onChange={(event) => onChange({ ...filters, action: event.target.value })}
          className="rounded-control border border-border bg-surface px-2 py-1.5 text-sm text-fg"
        >
          <option value="">All actions</option>
          {ACTIVITY_ACTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <form role="search" onSubmit={submitActor} className="flex flex-wrap items-end gap-2">
        <label className="grid gap-1 text-sm text-muted">
          Who
          <input
            type="text"
            value={actorDraft}
            maxLength={ACTOR_MAX_LENGTH}
            placeholder="Username"
            onChange={(event) => setActorDraft(event.target.value)}
            className="rounded-control border border-border bg-surface px-2 py-1.5 text-sm text-fg"
          />
        </label>
        <Button type="submit" size="sm" variant="secondary">
          Filter
        </Button>
      </form>
      {filtered && (
        <button
          type="button"
          className={buttonClass({ variant: "ghost", size: "sm" })}
          onClick={() => {
            setActorDraft("");
            onChange(NO_FILTERS);
          }}
        >
          Clear filters
        </button>
      )}
    </div>
  );
}
