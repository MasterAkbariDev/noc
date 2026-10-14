import type { EventView } from "../../api/types";
import { Section } from "../../ui/Section";
import { Timeline } from "./Timeline";

export function TimelineTab({ events }: { events: EventView[] }) {
  return (
    <Section heading="Events">
      <Timeline events={events} />
    </Section>
  );
}
