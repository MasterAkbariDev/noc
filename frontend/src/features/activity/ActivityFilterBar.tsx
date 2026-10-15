import { useState, type FormEvent } from "react";
import { Button, Field, FilterBar, Form, Select, TextInput } from "../../ui";
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
    <FilterBar>
      <Field label="Action" compact>
        <Select
          compact
          value={filters.action}
          options={[{ value: "", label: "All actions" }, ...ACTIVITY_ACTIONS]}
          onChange={(event) => onChange({ ...filters, action: event.target.value })}
        />
      </Field>
      <Form role="search" onSubmit={submitActor} className="flex flex-wrap items-end gap-2">
        <Field label="Who" compact>
          <TextInput
            compact
            value={actorDraft}
            maxLength={ACTOR_MAX_LENGTH}
            placeholder="Username"
            onChange={(event) => setActorDraft(event.target.value)}
          />
        </Field>
        <Button type="submit" size="sm" variant="secondary">
          Filter
        </Button>
      </Form>
      {filtered && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setActorDraft("");
            onChange(NO_FILTERS);
          }}
        >
          Clear filters
        </Button>
      )}
    </FilterBar>
  );
}
