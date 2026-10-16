import type { CommandStep } from "../../api/fleet";
import { CommandLine } from "../../ui/CommandLine";
import { Field, TextInput } from "../../ui/Form";
import { List, ListItem } from "../../ui/List";

const CODE_MAX_LENGTH = 16;

export function CodeField({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <Field label="Authentication code" hint="Every change to keys and servers asks for a fresh code from your app.">
      <TextInput
        name="fleet-code"
        inputMode="numeric"
        autoComplete="one-time-code"
        required
        maxLength={CODE_MAX_LENGTH}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </Field>
  );
}

export function StepsList({ steps }: { steps: CommandStep[] }) {
  if (steps.length === 0) {
    return <p className="m-0 text-sm text-muted">Nothing to run on a server.</p>;
  }
  return (
    <List variant="numbered" gap="md" label="Commands to run">
      {steps.map((step) => (
        <ListItem key={`${step.title}-${step.where}`}>
          <p className="m-0 text-sm font-medium">{step.title}</p>
          <p className="m-0 text-xs text-muted">Run {step.where}.</p>
          <CommandLine command={step.command} />
        </ListItem>
      ))}
    </List>
  );
}
