import { Bell, CircleCheck, Clock, Inbox, Server, Settings, Siren, Users } from "lucide-react";
import { useState } from "react";
import { ThemeToggle } from "../components/ThemeToggle";
import { DonutChart } from "../ui/charts";
import {
  Alert,
  Badge,
  Button,
  ButtonLink,
  Card,
  Checkbox,
  DescriptionList,
  DataTable,
  Dialog,
  EmptyState,
  ErrorState,
  Field,
  FieldNote,
  Form,
  FormActions,
  FormMessage,
  HealthBadge,
  IconButton,
  IncidentStatusBadge,
  KpiTile,
  List,
  ListItem,
  Menu,
  Meter,
  type MenuItem,
  PageHeader,
  RelativeTime,
  Section,
  SegmentedControl,
  Select,
  SeverityBadge,
  Skeleton,
  StatusDot,
  Tabs,
  Term,
  TextArea,
  TextInput,
  Tooltip,
  useToast,
} from "../ui";

const TONES = ["critical", "warning", "info", "ok", "neutral", "unknown"] as const;
const BUTTON_VARIANTS = ["primary", "secondary", "ghost", "danger", "link"] as const;

type SampleRow = { id: string; name: string; state: string };

const SAMPLE_ROWS: SampleRow[] = [
  { id: "1", name: "demo-1", state: "ESCALATED" },
  { id: "2", name: "noc", state: "RESOLVED" },
];

const SAMPLE_TIME = new Date(Date.now() - 12 * 60_000).toISOString();

const MENU_ITEMS: MenuItem[] = [
  { key: "settings", label: "Settings", icon: Settings, onSelect: () => undefined },
  { key: "users", label: "Users", icon: Users, onSelect: () => undefined },
  { key: "remove", label: "Remove", danger: true, onSelect: () => undefined },
];

function ToastDemo() {
  const toast = useToast();
  return (
    <div className="flex flex-wrap gap-2">
      <Button size="sm" onClick={() => toast.success("Saved the change.")}>
        Success toast
      </Button>
      <Button size="sm" variant="danger" onClick={() => toast.error("Could not save.")}>
        Error toast
      </Button>
    </div>
  );
}

function DialogDemo() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Open dialog
      </Button>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title="Mark incident resolved?"
        description="The close form lives in this dialog."
      >
        <p className="m-0 text-sm">Dialog body. Escape or the close button dismisses it.</p>
      </Dialog>
    </>
  );
}

function TabsDemo() {
  const [tab, setTab] = useState("one");
  return (
    <Tabs
      label="Sample tabs"
      value={tab}
      onValueChange={setTab}
      items={[
        { value: "one", label: "Evidence", content: <p className="m-0 text-sm">First tab content.</p> },
        { value: "two", label: "Report", content: <p className="m-0 text-sm">Second tab content.</p> },
      ]}
    />
  );
}

function ButtonsSection() {
  return (
    <div className="flex flex-wrap gap-2">
      {BUTTON_VARIANTS.map((variant) => (
        <Button key={variant} variant={variant}>
          {variant}
        </Button>
      ))}
      <Button size="sm" disabled>
        disabled
      </Button>
    </div>
  );
}

function BadgesSection() {
  return (
    <div className="flex flex-wrap gap-2">
      {TONES.map((tone) => (
        <Badge key={tone} tone={tone} icon={Clock}>
          {tone}
        </Badge>
      ))}
      <SeverityBadge severity="critical" />
      <SeverityBadge severity="warning" />
      <SeverityBadge severity="info" />
      <IncidentStatusBadge status="ESCALATED" />
      <IncidentStatusBadge status="RESOLVED" />
      <IncidentStatusBadge status="INVESTIGATING" />
      <HealthBadge status="ok" />
      <HealthBadge status="degraded" />
      <HealthBadge status="down" />
      <HealthBadge status="unknown" />
    </div>
  );
}

function DotsSection() {
  return (
    <div className="flex flex-wrap gap-4 text-sm">
      {TONES.map((tone) => (
        <StatusDot key={tone} tone={tone} label={tone} showLabel />
      ))}
    </div>
  );
}

function TermSection() {
  return (
    <p className="m-0 text-sm">
      Root cause: <Term technical="disk_full_logs">logs filling the disk</Term>, and automatic actions are{" "}
      <Term technical="execution_disabled">switched off</Term>.
    </p>
  );
}

function TooltipSection() {
  return (
    <Tooltip content="Hover or focus text shows the raw value.">
      <Button size="sm" variant="ghost">
        Tooltip target
      </Button>
    </Tooltip>
  );
}

function FormSection() {
  const [show, setShow] = useState("open");
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card title="Form controls">
        <Form onSubmit={(event) => event.preventDefault()}>
          <Field label="Username">
            <TextInput placeholder="alice" />
          </Field>
          <Field
            label={
              <span>
                Password <FieldNote>(12 to 128 characters)</FieldNote>
              </span>
            }
          >
            <TextInput type="password" />
          </Field>
          <Field label="Role" hint="Admins can change accounts.">
            <Select
              options={[
                { value: "viewer", label: "Viewer" },
                { value: "admin", label: "Admin" },
              ]}
            />
          </Field>
          <Field label="Note">
            <TextArea rows={3} />
          </Field>
          <Checkbox label="I checked this incident" hint="required" />
          <FormMessage>Invalid username or password.</FormMessage>
          <FormActions align="end">
            <Button>Cancel</Button>
            <Button type="submit" variant="primary">
              Save
            </Button>
          </FormActions>
        </Form>
      </Card>
      <div className="grid content-start gap-4">
        <Card title="Segmented control and icon button">
          <div className="flex flex-wrap items-center gap-3">
            <SegmentedControl
              label="Show"
              value={show}
              onChange={setShow}
              segments={[
                { value: "open", label: "Open" },
                { value: "all", label: "All" },
              ]}
            />
            <IconButton label="Notifications" icon={Bell} variant="secondary" />
            <ButtonLink to="/" size="sm">
              Link as button
            </ButtonLink>
          </div>
        </Card>
        <Card title="Meters and facts">
          <div className="grid gap-3">
            <Meter label="CPU" value={42} valueText="42%" />
            <Meter label="Disk" value={93} valueText="93%" tone="critical" />
            <DescriptionList
              items={[
                { key: "a", term: "Endpoint", detail: "https://api.example.com" },
                { key: "b", term: "Proxy", detail: "none" },
              ]}
            />
            <List variant="bullet" gap="xs">
              <ListItem>First reason</ListItem>
              <ListItem>Second reason</ListItem>
            </List>
          </div>
        </Card>
      </div>
    </div>
  );
}

function AlertsSection() {
  return (
    <div className="grid gap-3">
      {TONES.map((tone) => (
        <Alert key={tone} tone={tone} title={`A ${tone} message`}>
          <p className="m-0">The body explains what happened and what to do.</p>
        </Alert>
      ))}
    </div>
  );
}

export function UiKitPage() {
  return (
    <>
      <PageHeader
        title="UI kit"
        status="Development-only page for the visual check in light and dark."
        actions={<ThemeToggle />}
      />

      <Section heading="Buttons">
        <ButtonsSection />
      </Section>

      <Section heading="Badges, severity, status and health">
        <BadgesSection />
        <DotsSection />
      </Section>

      <Section heading="Plain language with the technical term">
        <TermSection />
        <TooltipSection />
      </Section>

      <Section heading="Forms">
        <FormSection />
      </Section>

      <Section heading="Alerts">
        <AlertsSection />
      </Section>

      <Section heading="Donut chart">
        <DonutChart
          title="Server status"
          centerLabel="servers"
          firstColumn="Status"
          valueColumn="Servers"
          empty="No servers."
          items={[
            { key: "up", label: "Up", value: 3, color: "var(--ui-ok)" },
            { key: "down", label: "Down", value: 1, color: "var(--ui-critical)" },
            { key: "unknown", label: "Unknown", value: 1, color: "var(--ui-unknown)" },
          ]}
        />
      </Section>

      <Section heading="KPI tiles">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <KpiTile label="Open incidents" value={1} hint="1 needs you" tone="warning" to="/incidents" icon={Siren} trend={[0, 2, 1, 3, 1]} />
          <KpiTile label="Servers" value="2/2" hint="all up" tone="ok" to="/servers" icon={Server} />
          <KpiTile label="LLM keys" value="9/10" tone="warning" to="/system" />
          <KpiTile label="Failed checks" value={0} tone="critical" />
        </div>
      </Section>

      <Section heading="Cards, menus and dialogs">
        <div className="grid gap-3 md:grid-cols-2">
          <Card
            title="Card with actions"
            actions={<Menu label="Actions" items={MENU_ITEMS} />}
          >
            <p className="m-0 text-sm">Card body text.</p>
          </Card>
          <Card title="Dialog and toast">
            <div className="flex flex-col items-start gap-3">
              <DialogDemo />
              <ToastDemo />
            </div>
          </Card>
        </div>
        <TabsDemo />
      </Section>

      <Section heading="Table">
        <DataTable<SampleRow>
          label="Sample servers"
          columns={[
            { key: "name", header: "Name", cell: (row) => row.name },
            { key: "state", header: "State", cell: (row) => <IncidentStatusBadge status={row.state} /> },
            { key: "seen", header: "Seen", cell: () => <RelativeTime iso={SAMPLE_TIME} /> },
          ]}
          rows={SAMPLE_ROWS}
          rowKey={(row) => row.id}
          empty="No servers."
        />
        <DataTable<SampleRow>
          label="Empty sample"
          columns={[{ key: "name", header: "Name", cell: (row) => row.name }]}
          rows={[]}
          rowKey={(row) => row.id}
          empty="Nothing to show."
        />
      </Section>

      <Section heading="States">
        <div className="grid gap-3 md:grid-cols-2">
          <Card title="Loading">
            <Skeleton lines={3} />
          </Card>
          <ErrorState title="Could not load" message="The NOC API did not answer." onRetry={() => undefined} />
          <Card>
            <EmptyState icon={Inbox} title="Nothing needs you right now." text="New escalations show up here." />
          </Card>
          <Card>
            <EmptyState icon={CircleCheck} title="All quiet." />
          </Card>
        </div>
      </Section>
    </>
  );
}
