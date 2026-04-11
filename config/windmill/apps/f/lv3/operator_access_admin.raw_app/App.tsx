import React, { ReactNode, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { Command } from "cmdk";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
  type ColDef,
  type GridApi,
  type GridReadyEvent,
  type ModelUpdatedEvent,
  type SelectionChangedEvent,
} from "ag-grid-community";
import { AgGridReact, type CustomCellRendererProps } from "ag-grid-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Editor } from "@tiptap/react";
import { EditorContent, useEditor } from "@tiptap/react";
import { Markdown } from "@tiptap/markdown";
import { Table } from "@tiptap/extension-table";
import TableCell from "@tiptap/extension-table-cell";
import TableHeader from "@tiptap/extension-table-header";
import TableRow from "@tiptap/extension-table-row";
import TaskItem from "@tiptap/extension-task-item";
import TaskList from "@tiptap/extension-task-list";
import StarterKit from "@tiptap/starter-kit";
import { Controller, useForm } from "react-hook-form";
import type { Tour } from "shepherd.js";
import {
  OffboardFormValues,
  offboardFormDefaults,
  offboardFormSchema,
  OnboardFormValues,
  onboardFormDefaults,
  onboardFormSchema,
  SyncFormValues,
  syncFormDefaults,
  syncFormSchema,
} from "./schemas";
import { backend } from "./wmill";
import {
  CHECKLIST_ITEMS,
  canonicalJourneyUrl,
  completeChecklistItem,
  createFlowId,
  emitJourneyEvent,
  readJourneyProgress,
  recordInitialSessionStart,
  type ChecklistItemId,
  type JourneyProgress,
  type JourneyEventInput,
} from "./journeyAnalytics";
import {
  DOCS_BASE_URL,
  paletteKindLabels,
  paletteLaneLabels,
  paletteStaticEntries,
  readPaletteStorageState,
  recordPaletteRecent,
  togglePaletteFavorite,
  type PaletteEntrySeed,
  type PaletteSearchResult,
  type PaletteStorageState,
} from "./commandPalette";
import {
  readTourProgress,
  startOperatorAccessTour,
  tourIntentLabel,
  writeTourProgress,
  type TourIntent,
  type TourProgress,
} from "./touring";
import "./index.css";

ModuleRegistry.registerModules([AllCommunityModule]);

type OperatorRecord = {
  id: string;
  name: string;
  email: string;
  role: string;
  status: string;
  notes?: string;
  keycloak_username: string;
  realm_roles: string[];
  groups: string[];
  tailscale_login_email: string;
  ssh_enabled: boolean;
  onboarded_at: string;
  offboarded_at?: string;
  last_reviewed_at?: string;
  last_seen_at?: string;
};

type RosterPayload = {
  status: string;
  operator_count: number;
  active_count: number;
  inactive_count: number;
  operators: OperatorRecord[];
};

type RosterPayloadError = {
  status?: string;
  reason?: string;
  stderr?: string;
  error?: string;
  message?: string;
};

type ActionPayload = {
  status: string;
  returncode: number;
  stdout?: string;
  stderr?: string;
  result?: unknown;
};

type InventoryPayload = {
  status: string;
  returncode: number;
  stdout?: string;
  stderr?: string;
  result?: unknown;
};

type TourLaunchOptions = {
  autoPrompted?: boolean;
  resume?: boolean;
};

type FieldShellProps = {
  htmlFor: string;
  label: string;
  hint: string;
  error?: string;
  touched?: boolean;
  required?: boolean;
  stretch?: boolean;
  tourTarget?: string;
  children: ReactNode;
};

type FormStatusProps = {
  isSubmitting: boolean;
  isDirty: boolean;
  submitCount: number;
  errorCount: number;
  idleMessage: string;
  helpHref: string;
  helpLabel: string;
};

type ToolbarButtonProps = {
  label: string;
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
};

type QueryFeedback = {
  label: string;
  toneClass: string;
  detail: string;
};

type ActionResultState = {
  title: string;
  kind: "idle" | "pending" | "success" | "error";
  payload?: unknown;
  error?: string;
  updatedAt?: number;
};

type UpdateNotesMutationInput = {
  operator_id: string;
  notes_markdown: string;
  dry_run: boolean;
};

type GuidanceLink = {
  label: string;
  href: string;
};

type CanonicalPageStateKind =
  | "loading"
  | "background_refresh"
  | "empty"
  | "partial_or_degraded"
  | "success"
  | "validation_error"
  | "system_error"
  | "unauthorized"
  | "not_found";

type CanonicalPageState = {
  kind: CanonicalPageStateKind;
  badgeLabel: string;
  title: string;
  summary: string;
  detail?: string;
  nextSteps: string[];
  helpLinks: GuidanceLink[];
};

const CANONICAL_PAGE_STATES: ReadonlyArray<CanonicalPageStateKind> = [
  "loading",
  "background_refresh",
  "empty",
  "partial_or_degraded",
  "success",
  "validation_error",
  "system_error",
  "unauthorized",
  "not_found",
];

const RUNBOOK_URLS = {
  operatorAdmin: `${DOCS_BASE_URL}/runbooks/windmill-operator-access-admin/`,
  operatorOnboarding: `${DOCS_BASE_URL}/runbooks/operator-onboarding/`,
  operatorOffboarding: `${DOCS_BASE_URL}/runbooks/operator-offboarding/`,
  validation: `${DOCS_BASE_URL}/runbooks/validate-repository-automation/`,
} as const;

type CommandPaletteSearchPayload = {
  status: string;
  query: string;
  count: number;
  results: PaletteSearchResult[];
};

type CommandPaletteItem = PaletteEntrySeed & {
  onSelect: () => void;
  searchValue: string;
};

type CommandPaletteSection = {
  id: string;
  label: string;
  items: CommandPaletteItem[];
};

type JourneyScorecardMetric = {
  status: string;
  [key: string]: unknown;
};

type JourneyScorecardsReport = {
  status: string;
  generated_at: string;
  population: {
    visitors: number;
    sessions: number;
    events: number;
  };
  scorecards: {
    time_to_first_safe_action: JourneyScorecardMetric;
    onboarding_checklist_completion: JourneyScorecardMetric;
    search_to_destination_success: JourneyScorecardMetric;
    alert_handoffs: JourneyScorecardMetric;
    resumable_task_completion: JourneyScorecardMetric;
    help_to_successful_recovery: JourneyScorecardMetric;
  };
  route_aggregates: {
    status: string;
    pageviews?: Record<string, number>;
    reason?: string;
  };
  failure_signals: {
    glitchtip_events: number;
  };
};

type SearchFlowState = {
  flowId: string;
  startedAt: number;
  queryBucket: string;
};

type HelpFlowState = {
  flowId: string;
  openedAt: number;
  context: string;
};

type JourneyAlertState = {
  flowId: string;
  source: string;
  fingerprint: string;
  message: string;
  startedAt: number;
  acknowledgedAt?: number;
};

type TourFlowState = {
  flowId: string;
  intent: TourIntent;
  startedAt: number;
  resumed: boolean;
};
const operatorGridTheme = themeQuartz.withParams({
  spacing: 7,
  accentColor: "#a5411c",
  backgroundColor: "#fffaf2",
  foregroundColor: "#1c1a16",
  headerBackgroundColor: "#efe3d2",
  headerTextColor: "#4c4035",
  rowHoverColor: "rgba(165, 65, 28, 0.08)",
});

const queryKeys = {
  operatorRoster: () => ["operator-roster"] as const,
  operatorInventory: (operatorId: string) => ["operator-inventory", operatorId] as const,
  operatorInventoryRoot: () => ["operator-inventory"] as const,
  operatorJourneyScorecards: () => ["operator-journey-scorecards"] as const,
  commandPaletteSearch: (query: string) => ["command-palette-search", query] as const,
};

function isCommandPaletteSearchPayload(payload: unknown): payload is CommandPaletteSearchPayload {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const candidate = payload as Partial<CommandPaletteSearchPayload>;
  return candidate.status === "ok" && Array.isArray(candidate.results);
}

async function fetchCommandPaletteSearch(query: string): Promise<PaletteSearchResult[]> {
  const payload = await backend.command_palette_search({
    query,
    limit: 8,
  });
  if (!isCommandPaletteSearchPayload(payload)) {
    throw new Error("Windmill returned an invalid command palette search payload.");
  }
  return payload.results;
}

function buildPaletteSearchValue(item: PaletteEntrySeed): string {
  return [
    item.label,
    item.description,
    paletteLaneLabels[item.lane],
    paletteKindLabels[item.kind],
    ...(item.keywords ?? []),
  ]
    .join(" ")
    .trim();
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  if (target.closest("[cmdk-root]")) {
    return true;
  }
  return (
    target.isContentEditable ||
    target.tagName === "INPUT" ||
    target.tagName === "TEXTAREA" ||
    target.tagName === "SELECT"
  );
}

function ToolbarButton({ label, onClick, active = false, disabled = false }: ToolbarButtonProps) {
  return (
    <button
      type="button"
      className={`toolbarButton ${active ? "isActive" : ""}`}
      onClick={onClick}
      disabled={disabled}
    >
      {label}
    </button>
  );
}

function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function formatDate(value?: string | null): string {
  if (!value) {
    return "n/a";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function formatTimestamp(value?: number): string {
  if (!value) {
    return "not loaded yet";
  }
  return new Date(value).toLocaleTimeString();
}

function formatOperatorSearchText(operator: OperatorRecord): string {
  return [
    operator.name,
    operator.email,
    operator.role,
    operator.status,
    operator.keycloak_username,
    operator.realm_roles.join(" "),
    operator.groups.join(" "),
    operator.tailscale_login_email,
    operator.notes ?? "",
    operator.onboarded_at,
    operator.offboarded_at ?? "",
    operator.last_reviewed_at ?? "",
    operator.last_seen_at ?? "",
  ]
    .join(" ")
    .trim();
}

function pillToneClass(value: string): string {
  return value === "active" ? "pillActive" : "pillInactive";
}

function OperatorIdentityCell({ data }: CustomCellRendererProps<OperatorRecord>) {
  if (!data) {
    return null;
  }

  return (
    <div className="operatorIdentity">
      <span className="operatorPrimary">{data.name}</span>
      <span className="operatorSecondary">{data.email}</span>
    </div>
  );
}

function RoleCell({ value }: CustomCellRendererProps<OperatorRecord, string>) {
  return <span className="pill pillRole">{value ?? "n/a"}</span>;
}

function StatusCell({ value }: CustomCellRendererProps<OperatorRecord, string>) {
  const status = value ?? "unknown";
  return <span className={`pill ${pillToneClass(status)}`}>{status}</span>;
}

function KeycloakCell({ data }: CustomCellRendererProps<OperatorRecord>) {
  if (!data) {
    return null;
  }

  const roles = data.realm_roles.join(", ");
  return (
    <div className="operatorIdentity">
      <span className="operatorPrimary">{data.keycloak_username || "n/a"}</span>
      <span className="operatorSecondary">{roles || "no realm roles"}</span>
    </div>
  );
}

function TimestampCell({ value }: CustomCellRendererProps<OperatorRecord, string>) {
  return <span className="gridTimestamp">{formatDate(value)}</span>;
}

function extractRosterError(payload: RosterPayloadError): string {
  return payload.reason || payload.stderr || payload.error || payload.message || "Windmill returned an invalid operator roster payload.";
}

function extractCommandError(payload: Partial<ActionPayload> & RosterPayloadError): string {
  return payload.reason || payload.stderr || payload.error || payload.message || `Windmill returned status "${payload.status ?? "unknown"}".`;
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function isRosterPayload(payload: unknown): payload is RosterPayload {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const candidate = payload as Partial<RosterPayload>;
  return candidate.status === "ok" && Array.isArray(candidate.operators);
}

function setEditorMarkdown(editor: Editor | null, markdown: string) {
  if (!editor) {
    return;
  }
  if (editor.getMarkdown() === markdown) {
    return;
  }
  editor.commands.setContent(markdown, { contentType: "markdown" });
}

function assertActionOk(payload: ActionPayload, fallbackMessage: string): ActionPayload {
  if (payload.status !== "ok") {
    throw new Error(extractCommandError(payload));
  }
  if (payload.returncode !== 0) {
    throw new Error(payload.stderr || fallbackMessage);
  }
  return payload;
}

function getQueryFeedback(
  isPending: boolean,
  isFetching: boolean,
  isError: boolean,
  isStale: boolean,
  dataUpdatedAt: number,
  failureCount: number,
  cadence: string,
): QueryFeedback {
  if (isError) {
    return {
      label: "Error",
      toneClass: "pillDanger",
      detail: `Last good update ${formatTimestamp(dataUpdatedAt)}. Retries used: ${failureCount}. ${cadence}`,
    };
  }
  if (isPending) {
    return {
      label: "Loading",
      toneClass: "pillNeutral",
      detail: `Initial fetch in progress. ${cadence}`,
    };
  }
  if (isFetching) {
    return {
      label: "Refreshing",
      toneClass: "pillInfo",
      detail: `Showing cached data while a background refresh runs. ${cadence}`,
    };
  }
  if (isStale) {
    return {
      label: "Stale",
      toneClass: "pillWarning",
      detail: `Last updated ${formatTimestamp(dataUpdatedAt)}. ${cadence}`,
    };
  }
  return {
    label: "Fresh",
    toneClass: "pillFresh",
    detail: `Last updated ${formatTimestamp(dataUpdatedAt)}. ${cadence}`,
  };
}

function dedupeGuidanceLinks(links: GuidanceLink[]): GuidanceLink[] {
  return Array.from(new Map(links.map((link) => [link.href, link])).values());
}

function canonicalStateLabel(kind: CanonicalPageStateKind): string {
  switch (kind) {
    case "loading":
      return "Loading";
    case "background_refresh":
      return "Background Refresh";
    case "empty":
      return "Empty";
    case "partial_or_degraded":
      return "Partial / Degraded";
    case "success":
      return "Success";
    case "validation_error":
      return "Validation Error";
    case "system_error":
      return "System Error";
    case "unauthorized":
      return "Unauthorized";
    case "not_found":
      return "Not Found";
  }
}

function canonicalStateToneClass(kind: CanonicalPageStateKind): string {
  switch (kind) {
    case "success":
      return "pillSuccess";
    case "background_refresh":
      return "pillInfo";
    case "partial_or_degraded":
      return "pillWarning";
    case "validation_error":
    case "system_error":
    case "unauthorized":
    case "not_found":
      return "pillDanger";
    case "empty":
      return "pillRole";
    case "loading":
    default:
      return "pillNeutral";
  }
}

function canonicalStateBannerClass(kind: CanonicalPageStateKind): string {
  switch (kind) {
    case "success":
      return "banner bannerInline bannerSuccess";
    case "partial_or_degraded":
      return "banner bannerInline bannerWarning";
    case "validation_error":
    case "system_error":
    case "unauthorized":
    case "not_found":
      return "banner bannerInline bannerError";
    case "loading":
    case "background_refresh":
    case "empty":
    default:
      return "banner bannerInline bannerInfo";
  }
}

function buildCanonicalPageState(
  kind: CanonicalPageStateKind,
  title: string,
  summary: string,
  nextSteps: string[],
  helpLinks: GuidanceLink[],
  detail?: string,
): CanonicalPageState {
  return {
    kind,
    badgeLabel: canonicalStateLabel(kind),
    title,
    summary,
    detail,
    nextSteps,
    helpLinks: dedupeGuidanceLinks(helpLinks),
  };
}

function classifyFailureKind(message: string): "unauthorized" | "not_found" | "system_error" {
  const normalized = message.toLowerCase();
  if (/(401|403|unauthori[sz]ed|forbidden|permission|not allowed|access denied)/.test(normalized)) {
    return "unauthorized";
  }
  if (/(404|not found|unknown operator|missing raw app|no such script|missing route)/.test(normalized)) {
    return "not_found";
  }
  return "system_error";
}

function isValidationMessage(message: string): boolean {
  return /(validation|invalid|required|schema|zod|must |should |missing required|expected)/.test(message.toLowerCase());
}

function classifyActionFailureKind(message: string): "validation_error" | "unauthorized" | "not_found" | "system_error" {
  if (isValidationMessage(message)) {
    return "validation_error";
  }
  return classifyFailureKind(message);
}

function baseHelpLinks(...extraLinks: GuidanceLink[]): GuidanceLink[] {
  return dedupeGuidanceLinks([
    { label: "Operator admin runbook", href: RUNBOOK_URLS.operatorAdmin },
    { label: "Repository validation runbook", href: RUNBOOK_URLS.validation },
    ...extraLinks,
  ]);
}

function actionHelpLinks(title: string): GuidanceLink[] {
  if (title.includes("onboarding")) {
    return baseHelpLinks({ label: "Operator onboarding runbook", href: RUNBOOK_URLS.operatorOnboarding });
  }
  if (title.includes("off-boarding")) {
    return baseHelpLinks({ label: "Operator off-boarding runbook", href: RUNBOOK_URLS.operatorOffboarding });
  }
  return baseHelpLinks();
}

function formatDurationSeconds(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    return "n/a";
  }
  if (value < 60) {
    return `${Math.round(value)}s`;
  }
  const minutes = value / 60;
  if (minutes < 60) {
    return `${minutes.toFixed(1)}m`;
  }
  return `${(minutes / 60).toFixed(1)}h`;
}

function bucketSearchLength(value: string): string {
  const length = value.trim().length;
  if (length <= 0) {
    return "empty";
  }
  if (length <= 3) {
    return "1-3";
  }
  if (length <= 8) {
    return "4-8";
  }
  if (length <= 16) {
    return "9-16";
  }
  return "17+";
}

function assertScorecardsPayload(payload: unknown): JourneyScorecardsReport {
  if (!payload || typeof payload !== "object") {
    throw new Error("Windmill returned an invalid journey scorecards payload.");
  }
  const candidate = payload as Partial<JourneyScorecardsReport>;
  if (candidate.status !== "ok" || !candidate.scorecards || !candidate.population) {
    throw new Error("Windmill returned an incomplete journey scorecards payload.");
  }
  return candidate as JourneyScorecardsReport;
}

async function fetchRoster(): Promise<RosterPayload> {
  const payload = await backend.list_operators({});
  if (!isRosterPayload(payload)) {
    throw new Error(extractRosterError((payload ?? {}) as RosterPayloadError));
  }
  return payload;
}

async function fetchInventory(operatorId: string): Promise<InventoryPayload> {
  const payload = (await backend.operator_inventory({
    operator_id: operatorId,
    offline: false,
    dry_run: false,
  })) as InventoryPayload;
  return assertActionOk(payload as ActionPayload, "Windmill returned an invalid operator inventory payload.") as InventoryPayload;
}

async function fetchJourneyScorecards(): Promise<JourneyScorecardsReport> {
  const payload = await backend.journey_scorecards({
    window_days: 30,
    write_latest: true,
  });
  const report = (payload as { report?: unknown }).report ?? payload;
  return assertScorecardsPayload(report);
}

function FieldShell({
  htmlFor,
  label,
  hint,
  error,
  touched,
  required = false,
  stretch = false,
  tourTarget,
  children,
}: FieldShellProps) {
  const meta = error || (touched ? "Validated locally." : hint);
  const fieldClassName = [
    "formField",
    stretch ? "formFieldWide" : "",
    touched ? "isTouched" : "",
    error ? "isInvalid" : "",
  ]
    .filter(Boolean)
    .join(" ");
  const metaClassName = error ? "fieldMeta fieldMetaError" : touched ? "fieldMeta fieldMetaReady" : "fieldMeta";

  return (
    <div className={fieldClassName} data-tour-target={tourTarget}>
      <label htmlFor={htmlFor}>
        <span>{label}</span>
        {required ? <span className="labelTag">Required</span> : null}
      </label>
      {children}
      <div className={metaClassName}>{meta}</div>
    </div>
  );
}

function FormStatus({ isSubmitting, isDirty, submitCount, errorCount, idleMessage, helpHref, helpLabel }: FormStatusProps) {
  let className = "banner bannerInfo bannerInline";
  let message = idleMessage;

  if (isSubmitting) {
    className = "banner bannerInfo bannerInline";
    message = "Validating and submitting through the governed backend. Wait for the structured result panel before retrying.";
  } else if (submitCount > 0 && errorCount > 0) {
    className = "banner bannerError bannerInline";
    message =
      errorCount === 1
        ? "Resolve the highlighted field, then submit again."
        : `Resolve ${errorCount} highlighted fields, then submit again.`;
  } else if (isDirty) {
    className = "banner bannerInfo bannerInline";
    message = "Schema validation is active for this form. Touched fields update inline before the governed request is sent.";
  }

  return (
    <div className={`${className} formStatusBanner`}>
      <span>{message}</span>
      <a className="stateLink formStatusLink" href={helpHref} target="_blank" rel="noreferrer">
        {helpLabel}
      </a>
    </div>
  );
}

function StateGuidanceCard({
  state,
  compact = false,
  eyebrow,
}: {
  state: CanonicalPageState;
  compact?: boolean;
  eyebrow?: string;
}) {
  return (
    <div className={`stateCard ${compact ? "stateCardCompact" : ""}`} data-canonical-state={state.kind}>
      <div className="stateCardHeader">
        <div className="stateCardCopy">
          {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
          <div className="stateCardBadgeRow">
            <span className={`pill ${canonicalStateToneClass(state.kind)}`}>{state.badgeLabel}</span>
            {!compact ? <span className="muted">Next-best-action guidance</span> : null}
          </div>
          <h3>{state.title}</h3>
          <p>{state.summary}</p>
        </div>
      </div>
      {state.detail ? <div className={canonicalStateBannerClass(state.kind)}>{state.detail}</div> : null}
      <div className={`stateCardGrid ${compact ? "stateCardGridCompact" : ""}`}>
        <div>
          <h4>Next best action</h4>
          <ul className="stateList">
            {state.nextSteps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ul>
        </div>
        <div>
          <h4>Help and recovery</h4>
          <div className="stateLinks">
            {state.helpLinks.map((link) => (
              <a key={link.href} className="stateLink" href={link.href} target="_blank" rel="noreferrer">
                {link.label}
              </a>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function App() {
  const queryClient = useQueryClient();
  const [selectedOperatorId, setSelectedOperatorId] = useState("");
  const [quickFilterText, setQuickFilterText] = useState("");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteQuery, setPaletteQuery] = useState("");
  const [paletteState, setPaletteState] = useState<PaletteStorageState>(() => readPaletteStorageState());
  const [displayedOperatorCount, setDisplayedOperatorCount] = useState(0);
  const [mentionTarget, setMentionTarget] = useState("");
  const [notesMarkdown, setNotesMarkdown] = useState("");
  const gridApiRef = useRef<GridApi<OperatorRecord> | null>(null);
  const deferredQuickFilterText = useDeferredValue(quickFilterText);
  const deferredPaletteQuery = useDeferredValue(paletteQuery.trim());
  const [actionResult, setActionResult] = useState<ActionResultState>({
    title: "No action executed yet",
    kind: "idle",
  });
  const [journeyProgress, setJourneyProgress] = useState<JourneyProgress>(() => readJourneyProgress());
  const [helpDrawerOpen, setHelpDrawerOpen] = useState(false);
  const [activeAlert, setActiveAlert] = useState<JourneyAlertState | null>(null);
  const [tourProgress, setTourProgress] = useState<TourProgress>(() => readTourProgress());
  const [tourRunning, setTourRunning] = useState(false);
  const tourRef = useRef<Tour | null>(null);
  const sessionStartedRef = useRef(false);
  const searchFlowRef = useRef<SearchFlowState | null>(null);
  const helpFlowRef = useRef<HelpFlowState | null>(null);
  const alertFlowRef = useRef<JourneyAlertState | null>(null);
  const tourFlowRef = useRef<TourFlowState | null>(null);
  const lastQuickFilterValueRef = useRef("");
  const lastInventorySuccessRef = useRef(0);
  const lastActionStateRef = useRef<string>("");
  const lastAlertFingerprintRef = useRef("");
  const onboardForm = useForm<OnboardFormValues>({
    resolver: zodResolver(onboardFormSchema),
    defaultValues: onboardFormDefaults,
    mode: "onTouched",
  });
  const offboardForm = useForm<OffboardFormValues>({
    resolver: zodResolver(offboardFormSchema),
    defaultValues: offboardFormDefaults,
    mode: "onTouched",
  });
  const syncForm = useForm<SyncFormValues>({
    resolver: zodResolver(syncFormSchema),
    defaultValues: syncFormDefaults,
    mode: "onTouched",
  });

  const rosterQuery = useQuery({
    queryKey: queryKeys.operatorRoster(),
    queryFn: fetchRoster,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
  const inventoryQuery = useQuery({
    queryKey: queryKeys.operatorInventory(selectedOperatorId || "unselected"),
    queryFn: () => fetchInventory(selectedOperatorId),
    enabled: selectedOperatorId.length > 0,
    staleTime: 20_000,
    refetchInterval: selectedOperatorId ? 45_000 : false,
    retry: 1,
  });
  const scorecardsQuery = useQuery({
    queryKey: queryKeys.operatorJourneyScorecards(),
    queryFn: fetchJourneyScorecards,
    staleTime: 60_000,
    refetchInterval: 120_000,
    retry: 1,
  });
  const commandPaletteSearchQuery = useQuery({
    queryKey: queryKeys.commandPaletteSearch(deferredPaletteQuery),
    queryFn: () => fetchCommandPaletteSearch(deferredPaletteQuery),
    enabled: paletteOpen && deferredPaletteQuery.length >= 2,
    staleTime: 30_000,
  });

  const operators = rosterQuery.data?.operators ?? [];
  const selectedOperator = useMemo(
    () => operators.find((item) => item.id === selectedOperatorId) ?? null,
    [operators, selectedOperatorId],
  );
  const onboardRole = onboardForm.watch("role");
  const sshRequired = onboardRole !== "viewer";
  const offboardOperatorId = offboardForm.watch("operator_id");
  const canResumeTour = Boolean(
    tourProgress.lastIntent && tourProgress.lastStepId && tourProgress.lastOutcome === "dismissed",
  );
  const lastTourTimestamp = tourProgress.lastCompletedAt ?? tourProgress.lastDismissedAt;
  const selectedOperatorNotes = selectedOperator?.notes ?? "";
  const notesDirty = notesMarkdown !== selectedOperatorNotes;
  const defaultColDef = useMemo<ColDef<OperatorRecord>>(
    () => ({
      sortable: true,
      resizable: true,
      filter: "agTextColumnFilter",
      floatingFilter: true,
      flex: 1,
      minWidth: 140,
    }),
    [],
  );
  const rosterRowSelection = useMemo(
    () => ({
      mode: "singleRow" as const,
      checkboxes: false,
      enableClickSelection: true,
    }),
    [],
  );
  const rosterColumns = useMemo<ColDef<OperatorRecord>[]>(
    () => [
      {
        headerName: "Operator",
        field: "name",
        pinned: "left",
        minWidth: 260,
        sort: "asc",
        cellRenderer: OperatorIdentityCell,
        getQuickFilterText: ({ data }) => (data ? formatOperatorSearchText(data) : ""),
      },
      {
        headerName: "Role",
        field: "role",
        maxWidth: 150,
        cellRenderer: RoleCell,
      },
      {
        headerName: "Status",
        field: "status",
        maxWidth: 150,
        cellRenderer: StatusCell,
      },
      {
        headerName: "Keycloak",
        field: "keycloak_username",
        minWidth: 240,
        cellRenderer: KeycloakCell,
        getQuickFilterText: ({ data }) =>
          data ? [data.keycloak_username, data.realm_roles.join(" ")].filter(Boolean).join(" ") : "",
      },
      {
        headerName: "SSH",
        field: "ssh_enabled",
        maxWidth: 160,
        valueGetter: ({ data }) => (data?.ssh_enabled ? "enabled" : "not required"),
      },
      {
        headerName: "Onboarded",
        field: "onboarded_at",
        minWidth: 190,
        cellRenderer: TimestampCell,
      },
      {
        headerName: "Last Reviewed",
        field: "last_reviewed_at",
        hide: true,
        minWidth: 190,
        cellRenderer: TimestampCell,
      },
      {
        headerName: "Last Seen",
        field: "last_seen_at",
        hide: true,
        minWidth: 190,
        cellRenderer: TimestampCell,
      },
      {
        headerName: "Realm Roles",
        field: "realm_roles",
        hide: true,
        valueGetter: ({ data }) => data?.realm_roles.join(", ") ?? "",
      },
      {
        headerName: "Groups",
        field: "groups",
        hide: true,
        valueGetter: ({ data }) => data?.groups.join(", ") ?? "",
      },
      {
        headerName: "Tailscale Login",
        field: "tailscale_login_email",
        hide: true,
      },
      {
        headerName: "Notes",
        field: "notes",
        hide: true,
      },
    ],
    [],
  );
  const tourStatusLabel = tourRunning
    ? "Tour Running"
    : tourProgress.lastOutcome === "completed"
      ? "Completed"
      : tourProgress.lastOutcome === "dismissed"
        ? "Paused"
        : "Ready";

  function recordJourney(input: JourneyEventInput) {
    emitJourneyEvent(backend, input);
  }

  function markChecklist(itemId: ChecklistItemId, input: Omit<JourneyEventInput, "eventType" | "checklistItem">) {
    setJourneyProgress(completeChecklistItem(backend, itemId, input));
  }

  function openHelpDrawer(context: string) {
    setHelpDrawerOpen(true);
    if (helpFlowRef.current) {
      return;
    }
    const flowId = createFlowId();
    helpFlowRef.current = {
      flowId,
      openedAt: Date.now(),
      context,
    };
    recordJourney({
      eventType: "help_opened",
      stage: "help",
      milestone: "drawer_opened",
      result: "started",
      flowId,
      route: canonicalJourneyUrl("/journeys/operator-access-admin/help"),
      plausible: {
        pagePath: "/journeys/operator-access-admin/help",
        eventName: "Journey Help Opened",
      },
      properties: {
        help_context: context,
      },
    });
  }

  function completeHelpFlow(outcome: string) {
    if (!helpFlowRef.current) {
      return;
    }
    const durationMs = Date.now() - helpFlowRef.current.openedAt;
    recordJourney({
      eventType: "help_task_completed",
      stage: "help",
      milestone: outcome,
      result: "success",
      flowId: helpFlowRef.current.flowId,
      durationMs,
      route: canonicalJourneyUrl("/journeys/operator-access-admin/help-success"),
      plausible: {
        pagePath: "/journeys/operator-access-admin/help-success",
        eventName: "Journey Help Completed",
      },
      properties: {
        help_context: helpFlowRef.current.context,
      },
    });
    markChecklist("help_recovery", {
      stage: "help",
      milestone: outcome,
      route: canonicalJourneyUrl("/journeys/operator-access-admin/help-success"),
      durationMs,
      properties: {
        help_context: helpFlowRef.current.context,
      },
    });
    helpFlowRef.current = null;
    setHelpDrawerOpen(false);
  }

  function emitAlert(source: string, message: string) {
    const fingerprint = `${source}:${message}`;
    if (lastAlertFingerprintRef.current === fingerprint || alertFlowRef.current?.fingerprint === fingerprint) {
      return;
    }
    lastAlertFingerprintRef.current = fingerprint;
    const alertState: JourneyAlertState = {
      flowId: createFlowId(),
      source,
      fingerprint,
      message,
      startedAt: Date.now(),
    };
    alertFlowRef.current = alertState;
    setActiveAlert(alertState);
    recordJourney({
      eventType: "alert_emitted",
      stage: "alert",
      milestone: source,
      result: "error",
      flowId: alertState.flowId,
      route: canonicalJourneyUrl("/journeys/operator-access-admin/alert"),
      plausible: {
        pagePath: "/journeys/operator-access-admin/alert",
        eventName: "Journey Alert Emitted",
      },
      glitchtip: {
        requested: true,
        level: "error",
        message: `Journey alert emitted for ${source}`,
      },
      properties: {
        alert_source: source,
      },
    });
  }

  function acknowledgeActiveAlert() {
    if (!alertFlowRef.current || alertFlowRef.current.acknowledgedAt) {
      return;
    }
    const acknowledgedAt = Date.now();
    alertFlowRef.current = {
      ...alertFlowRef.current,
      acknowledgedAt,
    };
    setActiveAlert(alertFlowRef.current);
    recordJourney({
      eventType: "alert_acknowledged",
      stage: "alert",
      milestone: alertFlowRef.current.source,
      result: "acknowledged",
      flowId: alertFlowRef.current.flowId,
      durationMs: acknowledgedAt - alertFlowRef.current.startedAt,
      route: canonicalJourneyUrl("/journeys/operator-access-admin/alert"),
      plausible: {
        pagePath: "/journeys/operator-access-admin/alert",
        eventName: "Journey Alert Acknowledged",
      },
      properties: {
        alert_source: alertFlowRef.current.source,
      },
    });
  }

  function resolveActiveAlert(outcome: string) {
    if (!alertFlowRef.current) {
      return;
    }
    recordJourney({
      eventType: "alert_resolved",
      stage: "alert",
      milestone: outcome,
      result: "success",
      flowId: alertFlowRef.current.flowId,
      durationMs: Date.now() - alertFlowRef.current.startedAt,
      route: canonicalJourneyUrl("/journeys/operator-access-admin/alert"),
      plausible: {
        pagePath: "/journeys/operator-access-admin/alert",
        eventName: "Journey Alert Resolved",
      },
      properties: {
        alert_source: alertFlowRef.current.source,
      },
    });
    alertFlowRef.current = null;
    lastAlertFingerprintRef.current = "";
    setActiveAlert(null);
  }

  function updateDisplayedOperatorCount(api: GridApi<OperatorRecord>) {
    setDisplayedOperatorCount(api.getDisplayedRowCount());
  }

  function syncGridSelection(api: GridApi<OperatorRecord>) {
    if (!selectedOperatorId) {
      api.deselectAll();
      return;
    }
    const rowNode = api.getRowNode(selectedOperatorId);
    if (!rowNode) {
      api.deselectAll();
      return;
    }
    if (!rowNode.isSelected()) {
      rowNode.setSelected(true, true, "api");
    }
  }

  function handleGridReady(event: GridReadyEvent<OperatorRecord>) {
    gridApiRef.current = event.api;
    updateDisplayedOperatorCount(event.api);
    syncGridSelection(event.api);
  }

  function handleGridModelUpdated(event: ModelUpdatedEvent<OperatorRecord>) {
    updateDisplayedOperatorCount(event.api);
  }

  function handleGridSelectionChanged(event: SelectionChangedEvent<OperatorRecord>) {
    const nextOperator = event.api.getSelectedRows()[0];
    if (!nextOperator || nextOperator.id === selectedOperatorId) {
      return;
    }
    if (!selectOperator(nextOperator.id)) {
      syncGridSelection(event.api);
    }
  }

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({
        heading: {
          levels: [1, 2, 3],
        },
      }),
      Markdown,
      TaskList,
      TaskItem.configure({
        nested: true,
      }),
      Table.configure({
        resizable: true,
      }),
      TableRow,
      TableHeader,
      TableCell,
    ],
    content: "",
    contentType: "markdown",
    editorProps: {
      attributes: {
        class: "richTextContent",
      },
    },
    onUpdate({ editor: currentEditor }) {
      const nextMarkdown = currentEditor.getMarkdown();
      setNotesMarkdown((current) => (current === nextMarkdown ? current : nextMarkdown));
    },
  });

  useEffect(() => {
    if (!operators.length) {
      if (selectedOperatorId) {
        setSelectedOperatorId("");
      }
      if (
        offboardForm.getValues("operator_id") ||
        offboardForm.getValues("reason") ||
        offboardForm.getValues("dry_run")
      ) {
        offboardForm.reset(offboardFormDefaults);
      }
      return;
    }

    const hasSelectedOperator = operators.some((item) => item.id === selectedOperatorId);
    const nextSelectedOperatorId = !selectedOperatorId || !hasSelectedOperator ? operators[0].id : selectedOperatorId;
    if (nextSelectedOperatorId !== selectedOperatorId) {
      setSelectedOperatorId(nextSelectedOperatorId);
    }
    offboardForm.setValue("operator_id", nextSelectedOperatorId, {
      shouldValidate: offboardForm.formState.submitCount > 0,
    });
  }, [offboardForm, operators, selectedOperatorId]);

  useEffect(() => {
    setNotesMarkdown(selectedOperatorNotes);
    setMentionTarget(selectedOperator?.id ?? "");
  }, [selectedOperator?.id, selectedOperatorNotes]);

  useEffect(() => {
    if (!rosterQuery.isPending && !rosterQuery.isError && !sessionStartedRef.current) {
      sessionStartedRef.current = true;
      setJourneyProgress(recordInitialSessionStart(backend));
    }
  }, [rosterQuery.isError, rosterQuery.isPending]);

  useEffect(() => {
    setEditorMarkdown(editor, notesMarkdown);
  }, [editor, notesMarkdown]);

  useEffect(() => {
    const api = gridApiRef.current;
    if (!api) {
      return;
    }
    syncGridSelection(api);
    updateDisplayedOperatorCount(api);
  }, [operators, selectedOperatorId]);

  useEffect(() => {
    const nextValue = quickFilterText.trim();
    if (nextValue && !lastQuickFilterValueRef.current) {
      const flowId = createFlowId();
      searchFlowRef.current = {
        flowId,
        startedAt: Date.now(),
        queryBucket: bucketSearchLength(nextValue),
      };
      recordJourney({
        eventType: "search_started",
        stage: "search",
        milestone: "quick_filter_started",
        result: "started",
        flowId,
        route: canonicalJourneyUrl("/journeys/operator-access-admin/search"),
        plausible: {
          pagePath: "/journeys/operator-access-admin/search",
          eventName: "Journey Search Started",
        },
        properties: {
          query_bucket: bucketSearchLength(nextValue),
        },
      });
    }
    if (!nextValue) {
      searchFlowRef.current = null;
    }
    lastQuickFilterValueRef.current = nextValue;
  }, [quickFilterText]);

  useEffect(() => {
    if (inventoryQuery.dataUpdatedAt <= 0 || inventoryQuery.dataUpdatedAt === lastInventorySuccessRef.current) {
      return;
    }
    if (inventoryQuery.status !== "success") {
      return;
    }
    lastInventorySuccessRef.current = inventoryQuery.dataUpdatedAt;
    if (!journeyProgress.checklist.safe_first_task) {
      recordJourney({
        eventType: "safe_task_completed",
        stage: "safe_first_task",
        milestone: "inventory_reviewed",
        result: "success",
        route: canonicalJourneyUrl("/journeys/operator-access-admin/safe-task"),
        plausible: {
          pagePath: "/journeys/operator-access-admin/safe-task",
          eventName: "Journey Safe Task Completed",
        },
        properties: {
          task: "inventory_review",
        },
      });
      markChecklist("safe_first_task", {
        stage: "safe_first_task",
        milestone: "inventory_reviewed",
        route: canonicalJourneyUrl("/journeys/operator-access-admin/safe-task"),
        properties: {
          task: "inventory_review",
        },
      });
    }
    if (searchFlowRef.current) {
      const currentSearch = searchFlowRef.current;
      recordJourney({
        eventType: "search_destination_opened",
        stage: "search",
        milestone: "inventory_destination_opened",
        result: "success",
        flowId: currentSearch.flowId,
        durationMs: Date.now() - currentSearch.startedAt,
        route: canonicalJourneyUrl("/journeys/operator-access-admin/search-result"),
        plausible: {
          pagePath: "/journeys/operator-access-admin/search-result",
          eventName: "Journey Search Success",
        },
        properties: {
          query_bucket: currentSearch.queryBucket,
        },
      });
      markChecklist("search_success", {
        stage: "search",
        milestone: "inventory_destination_opened",
        route: canonicalJourneyUrl("/journeys/operator-access-admin/search-result"),
        durationMs: Date.now() - currentSearch.startedAt,
        properties: {
          query_bucket: currentSearch.queryBucket,
        },
      });
      searchFlowRef.current = null;
    }
    if (helpFlowRef.current) {
      completeHelpFlow("inventory_reviewed");
    }
    if (alertFlowRef.current) {
      resolveActiveAlert("inventory_refreshed");
    }
    void queryClient.invalidateQueries({ queryKey: queryKeys.operatorJourneyScorecards() });
  }, [inventoryQuery.dataUpdatedAt, inventoryQuery.status, journeyProgress.checklist.safe_first_task, queryClient]);

  useEffect(() => {
    return () => {
      if (!tourRef.current) {
        return;
      }
      tourRef.current.hide();
      tourRef.current.steps.forEach((step) => step.destroy());
      tourRef.current = null;
    };
  }, []);

  useEffect(() => {
    function handleGlobalPaletteShortcut(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((current) => !current);
        return;
      }
      if (
        event.key === "/" &&
        !event.metaKey &&
        !event.ctrlKey &&
        !event.altKey &&
        !isTypingTarget(event.target)
      ) {
        event.preventDefault();
        setPaletteOpen(true);
      }
    }

    document.addEventListener("keydown", handleGlobalPaletteShortcut);
    return () => document.removeEventListener("keydown", handleGlobalPaletteShortcut);
  }, []);

  useEffect(() => {
    if (!paletteOpen && paletteQuery) {
      setPaletteQuery("");
    }
  }, [paletteOpen, paletteQuery]);

  function launchTour(intent: TourIntent, options: TourLaunchOptions = {}) {
    if (tourRunning) {
      return;
    }
    const shouldMarkAutoPrompted = options.autoPrompted || tourProgress.autoPrompted;
    if (options.autoPrompted && !tourProgress.autoPrompted) {
      setTourProgress(writeTourProgress({ autoPrompted: true }));
    }
    if (tourRef.current) {
      tourRef.current.steps.forEach((step) => step.destroy());
      tourRef.current = null;
    }
    const activeTourFlow =
      options.resume && tourFlowRef.current
        ? {
            ...tourFlowRef.current,
            resumed: true,
          }
        : {
            flowId: createFlowId(),
            intent,
            startedAt: Date.now(),
            resumed: false,
          };
    tourFlowRef.current = activeTourFlow;
    recordJourney({
      eventType: options.resume ? "tour_resumed" : "tour_started",
      stage: "orientation",
      milestone: intent,
      result: options.resume ? "resumed" : "started",
      flowId: activeTourFlow.flowId,
      route: canonicalJourneyUrl(options.resume ? "/journeys/operator-access-admin/resume" : "/journeys/operator-access-admin/start"),
      plausible: {
        pagePath: options.resume ? "/journeys/operator-access-admin/resume" : "/journeys/operator-access-admin/start",
        eventName: options.resume ? "Journey Tour Resumed" : "Journey Tour Started",
      },
      properties: {
        tour_intent: intent,
        auto_prompted: shouldMarkAutoPrompted,
      },
    });
    tourRef.current = startOperatorAccessTour({
      intent,
      autoPrompted: shouldMarkAutoPrompted,
      resumeFromStepId: options.resume ? tourProgress.lastStepId : null,
      context: {
        intendedRole: intent === "onboard_viewer" ? "viewer" : onboardRole === "admin" ? "admin" : "operator",
        selectedOperatorName: selectedOperator?.name ?? null,
        selectedOperatorStatus: selectedOperator?.status ?? null,
        hasOperators: operators.length > 0,
      },
      onProgress: (progress) => {
        setTourProgress(progress);
        if (!tourFlowRef.current) {
          return;
        }
        if (progress.lastOutcome === "dismissed") {
          recordJourney({
            eventType: "tour_dismissed",
            stage: "orientation",
            milestone: intent,
            result: "dismissed",
            flowId: tourFlowRef.current.flowId,
            durationMs: Date.now() - tourFlowRef.current.startedAt,
            route: canonicalJourneyUrl("/journeys/operator-access-admin/resume"),
            plausible: {
              pagePath: "/journeys/operator-access-admin/resume",
              eventName: "Journey Tour Paused",
            },
            properties: {
              tour_intent: intent,
            },
          });
          return;
        }
        if (progress.lastOutcome === "completed") {
          recordJourney({
            eventType: "tour_completed",
            stage: "orientation",
            milestone: intent,
            result: "success",
            flowId: tourFlowRef.current.flowId,
            durationMs: Date.now() - tourFlowRef.current.startedAt,
            route: canonicalJourneyUrl("/journeys/operator-access-admin/checklist"),
            plausible: {
              pagePath: "/journeys/operator-access-admin/checklist",
              eventName: "Journey Tour Completed",
            },
            properties: {
              tour_intent: intent,
              resumed: tourFlowRef.current.resumed,
            },
          });
          markChecklist("orientation", {
            stage: "orientation",
            milestone: intent,
            route: canonicalJourneyUrl("/journeys/operator-access-admin/checklist"),
            durationMs: Date.now() - tourFlowRef.current.startedAt,
            properties: {
              tour_intent: intent,
              resumed: tourFlowRef.current.resumed,
            },
          });
          if (helpFlowRef.current) {
            completeHelpFlow("tour_completed");
          }
        }
      },
      onRunningChange: setTourRunning,
    });
  }

  useEffect(() => {
    if (!rosterQuery.isPending && !rosterQuery.isError && !tourProgress.autoPrompted && !tourRunning) {
      launchTour("first_run", { autoPrompted: true });
    }
  }, [rosterQuery.isError, rosterQuery.isPending, tourProgress.autoPrompted, tourRunning]);

  useEffect(() => {
    if (rosterQuery.error) {
      emitAlert("roster", getErrorMessage(rosterQuery.error));
    }
  }, [rosterQuery.error]);

  useEffect(() => {
    if (inventoryQuery.error) {
      emitAlert("inventory", getErrorMessage(inventoryQuery.error));
    }
  }, [inventoryQuery.error]);

  useEffect(() => {
    const fingerprint = `${actionResult.kind}:${actionResult.updatedAt ?? 0}:${actionResult.title}`;
    if (fingerprint === lastActionStateRef.current) {
      return;
    }
    lastActionStateRef.current = fingerprint;
    if (actionResult.kind === "error" && actionResult.error) {
      emitAlert("mutation", actionResult.error);
      return;
    }
    if (actionResult.kind === "success") {
      if (helpFlowRef.current) {
        completeHelpFlow("mutation_success");
      }
      if (alertFlowRef.current) {
        resolveActiveAlert("mutation_success");
      }
      void queryClient.invalidateQueries({ queryKey: queryKeys.operatorJourneyScorecards() });
    }
  }, [actionResult.error, actionResult.kind, actionResult.title, actionResult.updatedAt, queryClient]);

  function selectOperator(nextId: string) {
    if (nextId !== selectedOperatorId && notesDirty && !window.confirm("Discard unsaved note edits for the current operator?")) {
      return false;
    }
    setSelectedOperatorId(nextId);
    offboardForm.setValue("operator_id", nextId, {
      shouldTouch: true,
      shouldValidate: offboardForm.formState.submitCount > 0,
    });
    return true;
  }

  function closePalette() {
    setPaletteOpen(false);
  }

  function focusElementById(elementId: string, sectionSelector?: string) {
    if (sectionSelector) {
      document.querySelector(sectionSelector)?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }
    window.setTimeout(() => {
      const element = document.getElementById(elementId);
      if (element instanceof HTMLElement) {
        element.focus();
      }
    }, 40);
  }

  function openHref(href: string, newTab = false) {
    if (newTab) {
      window.open(href, "_blank", "noopener,noreferrer");
      return;
    }
    window.location.assign(href);
  }

  function runPaletteItem(item: CommandPaletteItem) {
    setPaletteState((current) => recordPaletteRecent(current, item.id));
    closePalette();
    item.onSelect();
  }

  function handlePaletteFavoriteToggle(itemId: string) {
    setPaletteState((current) => togglePaletteFavorite(current, itemId));
  }

  function toggleLink() {
    if (!editor) {
      return;
    }
    const activeHref = String(editor.getAttributes("link").href ?? "");
    const href = window.prompt("Enter a link URL. Leave blank to remove the current link.", activeHref || "https://");
    if (href === null) {
      return;
    }
    const normalized = href.trim();
    if (!normalized) {
      editor.chain().focus().unsetLink().run();
      return;
    }
    editor.chain().focus().extendMarkRange("link").setLink({ href: normalized }).run();
  }

  function insertOperatorMention(targetOperatorId: string) {
    if (!editor || !targetOperatorId) {
      return;
    }
    editor.chain().focus().insertContent(`@${targetOperatorId} `).run();
  }

  const onboardMutation = useMutation<ActionPayload, Error, OnboardFormValues>({
    mutationFn: async (values) => {
      const payload = (await backend.create_operator(values)) as ActionPayload;
      return assertActionOk(payload, "Operator onboarding failed.");
    },
    onMutate: (payload) => {
      setActionResult({
        title: "Operator onboarding result",
        kind: "pending",
        payload,
        updatedAt: Date.now(),
      });
    },
    onSuccess: async (payload, variables) => {
      setActionResult({
        title: "Operator onboarding result",
        kind: "success",
        payload,
        updatedAt: Date.now(),
      });
      if (!variables.dry_run) {
        onboardForm.reset({
          ...onboardFormDefaults,
          role: variables.role,
        });
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.operatorRoster() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.operatorInventoryRoot() }),
      ]);
    },
    onError: (error) => {
      setActionResult({
        title: "Operator onboarding result",
        kind: "error",
        error: getErrorMessage(error),
        updatedAt: Date.now(),
      });
    },
  });

  const offboardMutation = useMutation<ActionPayload, Error, OffboardFormValues>({
    mutationFn: async (values) => {
      const payload = (await backend.offboard_operator(values)) as ActionPayload;
      return assertActionOk(payload, "Operator off-boarding failed.");
    },
    onMutate: (payload) => {
      setActionResult({
        title: "Operator off-boarding result",
        kind: "pending",
        payload,
        updatedAt: Date.now(),
      });
    },
    onSuccess: async (payload, variables) => {
      setActionResult({
        title: "Operator off-boarding result",
        kind: "success",
        payload,
        updatedAt: Date.now(),
      });
      if (!variables.dry_run) {
        offboardForm.reset({
          ...offboardFormDefaults,
          operator_id: variables.operator_id,
        });
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.operatorRoster() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.operatorInventoryRoot() }),
      ]);
    },
    onError: (error) => {
      setActionResult({
        title: "Operator off-boarding result",
        kind: "error",
        error: getErrorMessage(error),
        updatedAt: Date.now(),
      });
    },
  });

  const syncMutation = useMutation<ActionPayload, Error, SyncFormValues>({
    mutationFn: async (values) => {
      const payload = (await backend.sync_operators(values)) as ActionPayload;
      return assertActionOk(payload, "Operator roster reconciliation failed.");
    },
    onMutate: (payload) => {
      setActionResult({
        title: "Operator roster reconciliation result",
        kind: "pending",
        payload,
        updatedAt: Date.now(),
      });
    },
    onSuccess: async (payload, variables) => {
      setActionResult({
        title: "Operator roster reconciliation result",
        kind: "success",
        payload,
        updatedAt: Date.now(),
      });
      if (!variables.dry_run) {
        syncForm.reset(syncFormDefaults);
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.operatorRoster() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.operatorInventoryRoot() }),
      ]);
    },
    onError: (error) => {
      setActionResult({
        title: "Operator roster reconciliation result",
        kind: "error",
        error: getErrorMessage(error),
        updatedAt: Date.now(),
      });
    },
  });

  const notesMutation = useMutation<ActionPayload, Error, UpdateNotesMutationInput>({
    mutationFn: async (payload) => {
      const response = (await backend.update_operator_notes(payload)) as ActionPayload;
      return assertActionOk(response, "Operator notes update failed.");
    },
    onMutate: (payload) => {
      setActionResult({
        title: "Operator notes update result",
        kind: "pending",
        payload,
        updatedAt: Date.now(),
      });
    },
    onSuccess: async (payload) => {
      setActionResult({
        title: "Operator notes update result",
        kind: "success",
        payload,
        updatedAt: Date.now(),
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.operatorRoster() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.operatorInventoryRoot() }),
      ]);
    },
    onError: (error) => {
      setActionResult({
        title: "Operator notes update result",
        kind: "error",
        error: getErrorMessage(error),
        updatedAt: Date.now(),
      });
    },
  });

  const handleOnboardSubmit = onboardForm.handleSubmit(async (values) => {
    await onboardMutation.mutateAsync(values);
  });

  const handleOffboardSubmit = offboardForm.handleSubmit(async (values) => {
    await offboardMutation.mutateAsync(values);
  });

  const handleSyncSubmit = syncForm.handleSubmit(async (values) => {
    await syncMutation.mutateAsync(values);
  });

  async function handleSaveNotes() {
    if (!selectedOperatorId) {
      return;
    }
    await notesMutation.mutateAsync({
      operator_id: selectedOperatorId,
      notes_markdown: notesMarkdown,
      dry_run: false,
    });
  }

  const actionLoading =
    onboardMutation.isPending || offboardMutation.isPending || syncMutation.isPending || notesMutation.isPending;
  const rosterFeedback = getQueryFeedback(
    rosterQuery.isPending,
    rosterQuery.isFetching,
    rosterQuery.isError,
    rosterQuery.isStale,
    rosterQuery.dataUpdatedAt,
    rosterQuery.failureCount,
    "Background refresh every 60 seconds with retry-on-failure.",
  );
  const inventoryFeedback =
    selectedOperatorId.length > 0
      ? getQueryFeedback(
          inventoryQuery.isPending,
          inventoryQuery.isFetching,
          inventoryQuery.isError,
          inventoryQuery.isStale,
          inventoryQuery.dataUpdatedAt,
          inventoryQuery.failureCount,
          "Background refresh every 45 seconds while an operator is selected.",
        )
      : {
          label: "Idle",
          toneClass: "pillNeutral",
          detail: "Select an operator to start live inventory polling.",
        };
  const scorecardsFeedback = getQueryFeedback(
    scorecardsQuery.isPending,
    scorecardsQuery.isFetching,
    scorecardsQuery.isError,
    scorecardsQuery.isStale,
    scorecardsQuery.dataUpdatedAt,
    scorecardsQuery.failureCount,
    "Journey scorecards refresh every 120 seconds and combine worker receipts with Plausible route aggregates.",
  );
  const actionResultPreview =
    actionResult.kind === "error"
      ? prettyJson({ status: "error", message: actionResult.error })
      : actionResult.payload
        ? prettyJson(actionResult.payload)
        : "Run an action to inspect the structured result here.";
  const onboardErrorCount = Object.keys(onboardForm.formState.errors).length;
  const offboardErrorCount = Object.keys(offboardForm.formState.errors).length;
  const syncErrorCount = Object.keys(syncForm.formState.errors).length;
  const validationIssues = [
    onboardForm.formState.submitCount > 0 && onboardErrorCount > 0 ? "Onboard Operator" : null,
    offboardForm.formState.submitCount > 0 && offboardErrorCount > 0 ? "Off-board Operator" : null,
    syncForm.formState.submitCount > 0 && syncErrorCount > 0 ? "Reconcile Roster" : null,
  ].filter(Boolean) as string[];
  const rosterState = useMemo(() => {
    if (rosterQuery.isPending && !operators.length) {
      return buildCanonicalPageState(
        "loading",
        "Loading the operator roster",
        "The page is fetching the repo-authoritative operator roster before governed actions are enabled.",
        [
          "Wait for the first roster response before attempting onboarding, off-boarding, or inventory review.",
          "If loading lasts longer than one refresh cycle, use Refresh once and then open the runbook before retrying.",
        ],
        baseHelpLinks({ label: "Operator onboarding runbook", href: RUNBOOK_URLS.operatorOnboarding }),
        "This panel unlocks after the Windmill roster script returns the latest governed payload.",
      );
    }
    if (rosterQuery.isError && !operators.length) {
      const message = getErrorMessage(rosterQuery.error);
      const helpLinks = baseHelpLinks({ label: "Operator onboarding runbook", href: RUNBOOK_URLS.operatorOnboarding });
      switch (classifyFailureKind(message)) {
        case "unauthorized":
          return buildCanonicalPageState(
            "unauthorized",
            "Windmill did not authorize roster access",
            "The page could not read the operator roster with the current browser session.",
            [
              "Refresh the Windmill session or sign in again before retrying the roster fetch.",
              "Avoid repeated mutations until the roster is visible again so you do not act on stale assumptions.",
            ],
            helpLinks,
            message,
          );
        case "not_found":
          return buildCanonicalPageState(
            "not_found",
            "The roster route or backing script was not found",
            "The page could not resolve the live roster endpoint it expects to call.",
            [
              "Refresh the page once to rule out a transient raw-app routing issue.",
              "If the same error repeats, replay the governed Windmill converge instead of editing the live app by hand.",
            ],
            helpLinks,
            message,
          );
        default:
          return buildCanonicalPageState(
            "system_error",
            "The roster fetch failed before the page could load",
            "The page cannot show current operators until the runtime or backend error is resolved.",
            [
              "Use Refresh once, then stop retrying if the same error returns.",
              "Hand off the raw error together with the current branch and selected task so the next operator can recover safely.",
            ],
            helpLinks,
            message,
          );
      }
    }
    if (!operators.length) {
      return buildCanonicalPageState(
        "empty",
        "No operators are listed yet",
        "The roster call succeeded, but it returned zero governed operators.",
        [
          "Start the onboarding workflow if you are intentionally bootstrapping the first operator.",
          "If you expected existing operators, confirm the merged roster in `config/operators.yaml` before making live changes.",
        ],
        baseHelpLinks({ label: "Operator onboarding runbook", href: RUNBOOK_URLS.operatorOnboarding }),
      );
    }
    if (rosterQuery.isError || rosterQuery.isStale) {
      return buildCanonicalPageState(
        "partial_or_degraded",
        "Showing the last known roster while freshness is degraded",
        "You can still review cached operator data, but the latest refresh did not complete cleanly.",
        [
          "Use the cached roster for read-only confirmation and refresh once when you are ready to retry.",
          "Before making a risky change, confirm the Latest Result and Selected Operator Inventory panels match your expectation.",
        ],
        baseHelpLinks(),
        `Last successful update ${formatTimestamp(rosterQuery.dataUpdatedAt)}.`,
      );
    }
    if (rosterQuery.isFetching) {
      return buildCanonicalPageState(
        "background_refresh",
        "Roster refresh is running in the background",
        "The page is keeping the current roster visible while it checks for fresher data.",
        [
          "Keep working from the visible roster unless the state changes to partial or system error.",
          "Review the Selected Operator Inventory panel after any mutation so the refresh has time to settle.",
        ],
        baseHelpLinks(),
        rosterFeedback.detail,
      );
    }
    return buildCanonicalPageState(
      "success",
      "The roster is fresh and ready for governed work",
      "Current operator data is loaded and the page can safely guide onboarding, off-boarding, reconciliation, and notes review.",
      [
        "Use Quick Filter or row selection to focus the exact operator you intend to review or change.",
        "After each mutation, review the structured Latest Result and Selected Operator Inventory panels before moving on.",
      ],
      baseHelpLinks(),
      rosterFeedback.detail,
    );
  }, [operators.length, rosterFeedback.detail, rosterQuery.dataUpdatedAt, rosterQuery.error, rosterQuery.isError, rosterQuery.isFetching, rosterQuery.isPending, rosterQuery.isStale]);
  const inventoryState = useMemo(() => {
    if (!selectedOperatorId) {
      return buildCanonicalPageState(
        "empty",
        "Select an operator to inspect live inventory",
        "The inventory panel only starts polling after one operator is selected from the roster.",
        [
          "Choose one operator row first so the page can scope the governed inventory lookup safely.",
          "After a mutation succeeds, return here to confirm the resulting access state for that same operator.",
        ],
        baseHelpLinks(),
      );
    }
    if (inventoryQuery.isPending && !inventoryQuery.data) {
      return buildCanonicalPageState(
        "loading",
        "Loading the selected operator inventory",
        "The page is waiting for the governed inventory check to return the latest access view.",
        [
          "Wait for the first inventory response before deciding whether the access state matches the requested change.",
          "If the query stalls, refresh the inventory once rather than changing the selected operator repeatedly.",
        ],
        baseHelpLinks(),
      );
    }
    if (inventoryQuery.isError && !inventoryQuery.data) {
      const message = getErrorMessage(inventoryQuery.error);
      switch (classifyFailureKind(message)) {
        case "unauthorized":
          return buildCanonicalPageState(
            "unauthorized",
            "Inventory access is permission-limited",
            "The page could not read the selected operator inventory with the current session.",
            [
              "Refresh the Windmill session or confirm you are still signed in with the expected admin identity.",
              "Do not assume the operator state changed until the inventory panel can read live data again.",
            ],
            baseHelpLinks(),
            message,
          );
        case "not_found":
          return buildCanonicalPageState(
            "not_found",
            "The selected operator could not be found for inventory review",
            "The roster selection no longer maps cleanly to a live inventory target.",
            [
              "Refresh the roster and reselect the operator to confirm the ID still exists.",
              "If the operator was intentionally removed, move to another row instead of retrying this lookup.",
            ],
            baseHelpLinks({ label: "Operator off-boarding runbook", href: RUNBOOK_URLS.operatorOffboarding }),
            message,
          );
        default:
          return buildCanonicalPageState(
            "system_error",
            "The inventory check failed",
            "The page could not fetch the latest live access inventory for the selected operator.",
            [
              "Retry the inventory check once and then stop if the same runtime error repeats.",
              "Include the selected operator ID and the Latest Result payload in any handoff so recovery can start from context, not guesswork.",
            ],
            baseHelpLinks(),
            message,
          );
      }
    }
    if (inventoryQuery.isError || inventoryQuery.isStale) {
      return buildCanonicalPageState(
        "partial_or_degraded",
        "Inventory is visible, but the newest refresh is degraded",
        "You still have a recent access view, but the page cannot guarantee it is the newest one available.",
        [
          "Use the visible inventory for read-only confirmation and refresh once when you need a fresher answer.",
          "If you just ran a mutation, wait for the background refresh to complete before you conclude the platform drifted.",
        ],
        baseHelpLinks(),
        `Last successful update ${formatTimestamp(inventoryQuery.dataUpdatedAt)}.`,
      );
    }
    if (inventoryQuery.isFetching) {
      return buildCanonicalPageState(
        "background_refresh",
        "Inventory is refreshing in the background",
        "The page is keeping the last inventory response visible while it checks for changes.",
        [
          "Keep the same operator selected until the refresh completes so the comparison stays stable.",
          "Use Refresh Inventory only when you need an immediate recheck after a governed action.",
        ],
        baseHelpLinks(),
        inventoryFeedback.detail,
      );
    }
    return buildCanonicalPageState(
      "success",
      "Inventory is current for the selected operator",
      "The live access inventory has loaded successfully for the selected roster entry.",
      [
        "Compare this inventory with the Latest Result payload after each governed mutation.",
        "Switch operators only after you have captured or handed off the context you need from this one.",
      ],
      baseHelpLinks(),
      inventoryFeedback.detail,
    );
  }, [inventoryFeedback.detail, inventoryQuery.data, inventoryQuery.dataUpdatedAt, inventoryQuery.error, inventoryQuery.isError, inventoryQuery.isFetching, inventoryQuery.isPending, inventoryQuery.isStale, selectedOperatorId]);
  const notesState = useMemo(() => {
    if (!selectedOperator) {
      return buildCanonicalPageState(
        "empty",
        "Select one operator to unlock rich notes",
        "The notes editor stays empty until one roster row is selected.",
        [
          "Choose the operator you want to brief, review, or hand off before writing notes.",
          "Use Quick Filter first if you need to narrow the roster before selecting a person.",
        ],
        baseHelpLinks(),
      );
    }
    if (notesMutation.isPending) {
      return buildCanonicalPageState(
        "loading",
        "Saving note changes through the governed backend",
        "The editor is persisting markdown-backed notes for the selected operator.",
        [
          "Wait for the Latest Result panel before switching operators or refreshing the page.",
          "After the save completes, confirm the draft and saved state match before moving on.",
        ],
        baseHelpLinks(),
      );
    }
    if (actionResult.title === "Operator notes update result" && actionResult.kind === "error" && actionResult.error) {
      const message = actionResult.error;
      const kind = classifyActionFailureKind(message);
      switch (kind) {
        case "validation_error":
          return buildCanonicalPageState(
            "validation_error",
            "The notes payload needs attention before it can be saved",
            "The backend rejected the current note content or metadata.",
            [
              "Review the markdown source for malformed or incomplete content, then retry the save once.",
              "If the same validation issue returns, hand off the markdown and structured result instead of editing the repo state directly.",
            ],
            baseHelpLinks(),
            message,
          );
        case "unauthorized":
          return buildCanonicalPageState(
            "unauthorized",
            "The page could not save notes with the current session",
            "Your browser session no longer has permission to persist notes for this operator.",
            [
              "Refresh the Windmill session before retrying the save.",
              "Do not discard the current markdown until the saved result is confirmed again.",
            ],
            baseHelpLinks(),
            message,
          );
        case "not_found":
          return buildCanonicalPageState(
            "not_found",
            "The selected operator is no longer available for note updates",
            "The saved target changed or disappeared while you were editing notes.",
            [
              "Refresh the roster and confirm you still have the intended operator selected.",
              "Copy the markdown out before switching rows if you need to preserve the draft for handoff.",
            ],
            baseHelpLinks(),
            message,
          );
        default:
          return buildCanonicalPageState(
            "system_error",
            "The note save failed",
            "The editor still has your draft, but the governed backend did not accept the update.",
            [
              "Retry the save once after the runtime settles; then stop if the same error repeats.",
              "Use Reset only after you have captured the markdown you want to preserve for a handoff.",
            ],
            baseHelpLinks(),
            message,
          );
      }
    }
    if (notesDirty) {
      return buildCanonicalPageState(
        "partial_or_degraded",
        "Your notes draft is ahead of the saved state",
        "The editor contains unsaved changes for the selected operator.",
        [
          "Choose Save Notes when the draft is ready, or Reset if you want to return to the last saved markdown.",
          "Avoid switching operators until you either save the draft or intentionally discard it.",
        ],
        baseHelpLinks(),
      );
    }
    return buildCanonicalPageState(
      "success",
      "Notes match the saved markdown",
      "The rich editor and markdown source are aligned with the current saved note for this operator.",
      [
        "Use the rich editor for context and the markdown pane for exact handoff text when needed.",
        "Save again after each meaningful edit so later operators inherit the same governed context.",
      ],
      baseHelpLinks(),
    );
  }, [actionResult.error, actionResult.kind, actionResult.title, notesDirty, notesMutation.isPending, selectedOperator]);
  const resultState = useMemo(() => {
    const helpLinks = actionHelpLinks(actionResult.title);
    if (actionResult.kind === "idle") {
      return buildCanonicalPageState(
        "empty",
        "No governed action has been run yet",
        "The structured result panel stays empty until you submit a form or save notes.",
        [
          "Run one governed action from the forms or notes editor to capture a structured backend response here.",
          "After a success or failure, use this payload as the canonical handoff context instead of paraphrasing from memory.",
        ],
        helpLinks,
      );
    }
    if (actionResult.kind === "pending") {
      return buildCanonicalPageState(
        "loading",
        "A governed action is still running",
        "The backend is processing the latest request and the final structured result is not ready yet.",
        [
          "Wait for the final status here before retrying the same action.",
          "After the result lands, re-check the Selected Operator Inventory panel to confirm the live state.",
        ],
        helpLinks,
      );
    }
    if (actionResult.kind === "success") {
      return buildCanonicalPageState(
        "success",
        "The last governed action completed successfully",
        "This payload is the current source of truth for the most recent onboarding, off-boarding, reconciliation, or notes update request.",
        [
          "Review the structured output here before you move to another operator or task.",
          "Use the Selected Operator Inventory panel to confirm the corresponding live state after each mutation.",
        ],
        helpLinks,
        actionResult.updatedAt ? `Updated ${new Date(actionResult.updatedAt).toLocaleString()}.` : undefined,
      );
    }
    const errorMessage = actionResult.error ?? "Unknown action failure.";
    switch (classifyActionFailureKind(errorMessage)) {
      case "validation_error":
        return buildCanonicalPageState(
          "validation_error",
          "The last action was rejected by validation or input rules",
          "The backend did not accept the request payload as submitted.",
          [
            "Adjust the highlighted fields or payload assumptions, then resubmit once.",
            "If you still cannot proceed safely, hand off this structured error instead of retrying blind.",
          ],
          helpLinks,
          errorMessage,
        );
      case "unauthorized":
        return buildCanonicalPageState(
          "unauthorized",
          "The last action was permission-limited",
          "The request reached the backend, but the current session was not allowed to complete it.",
          [
            "Refresh the Windmill session or confirm the expected admin identity before retrying.",
            "Avoid repeated mutation attempts until the roster and inventory panels can read successfully again.",
          ],
          helpLinks,
          errorMessage,
        );
      case "not_found":
        return buildCanonicalPageState(
          "not_found",
          "The last action referenced a target that no longer exists",
          "The payload no longer mapped to a valid operator or runtime surface.",
          [
            "Refresh the roster and reselect the intended operator before retrying the action.",
            "If the operator was intentionally removed, capture this result in the handoff and continue with the updated roster.",
          ],
          helpLinks,
          errorMessage,
        );
      default:
        return buildCanonicalPageState(
          "system_error",
          "The last action failed at runtime",
          "The governed backend returned an operational error instead of a successful result.",
          [
            "Retry once after the runtime settles, then stop if the same error repeats.",
            "Include this structured result, the operator ID, and the selected task in any escalation or handoff.",
          ],
          helpLinks,
          errorMessage,
        );
    }
  }, [actionResult.error, actionResult.kind, actionResult.title, actionResult.updatedAt]);
  const pageState = useMemo(() => {
    const baseDetail = `This surface now maps all ${CANONICAL_PAGE_STATES.length} ADR 0315 states across its panels: Loading, Background Refresh, Empty, Partial / Degraded, Success, Validation Error, System Error, Unauthorized, and Not Found.`;
    if (rosterQuery.isPending && !operators.length) {
      return buildCanonicalPageState(
        "loading",
        "Operator admin is still assembling its first page state",
        "The page is waiting for the governed roster call before it can safely route you into task work.",
        [
          "Wait for the roster to load before deciding whether onboarding or inventory review is the next task.",
          "If the loading state persists, refresh once and then switch to the runbook-guided recovery path.",
        ],
        baseHelpLinks(),
        baseDetail,
      );
    }
    if (validationIssues.length) {
      return buildCanonicalPageState(
        "validation_error",
        "One or more forms still need valid input",
        "The page can continue, but at least one governed form is blocked by validation feedback.",
        [
          "Resolve the highlighted fields in the named forms before resubmitting.",
          "If you are unsure about the required values, use the linked runbooks or guided tours instead of guessing.",
        ],
        baseHelpLinks({ label: "Operator onboarding runbook", href: RUNBOOK_URLS.operatorOnboarding }),
        `Affected form states: ${validationIssues.join(", ")}. ${baseDetail}`,
      );
    }
    if (!operators.length) {
      return buildCanonicalPageState(
        "empty",
        "The page is ready, but the roster is empty",
        "This is a valid page state: the UI loaded successfully, yet there are no governed operators to work with.",
        [
          "Use the onboarding flow if you are intentionally creating the first operator.",
          "If this is unexpected, confirm the merged roster source before applying live changes.",
        ],
        baseHelpLinks({ label: "Operator onboarding runbook", href: RUNBOOK_URLS.operatorOnboarding }),
        baseDetail,
      );
    }
    if (actionLoading || rosterQuery.isFetching || inventoryQuery.isFetching) {
      return buildCanonicalPageState(
        "background_refresh",
        "The page is refreshing while keeping current context visible",
        "At least one governed query or mutation is still in flight, but the current surface remains usable.",
        [
          "Continue with read-only review while the refresh settles, then verify the Latest Result and Inventory panels.",
          "Avoid duplicate retries until the current action or refresh finishes.",
        ],
        baseHelpLinks(),
        baseDetail,
      );
    }
    if (
      rosterState.kind === "partial_or_degraded" ||
      inventoryState.kind === "partial_or_degraded" ||
      resultState.kind === "system_error" ||
      resultState.kind === "unauthorized" ||
      resultState.kind === "not_found" ||
      resultState.kind === "validation_error"
    ) {
      return buildCanonicalPageState(
        "partial_or_degraded",
        "The page is usable, but one or more task surfaces need recovery guidance",
        "A lower panel has richer detail about the current issue, so you can keep context without losing your place in the flow.",
        [
          "Follow the next-best-action guidance on the affected panel before running a new mutation.",
          "Use the structured Latest Result payload as the handoff record if you need another operator to continue safely.",
        ],
        baseHelpLinks(),
        baseDetail,
      );
    }
    return buildCanonicalPageState(
      "success",
      "The page is in a healthy guided-working state",
      "Roster, forms, notes, and inventory are aligned so you can move through the intended task flow without losing context.",
      [
        "Start from the roster, act through the governed form or notes workflow, and finish by checking Latest Result and Selected Operator Inventory.",
        "Use Guided Onboarding when the task is infrequent, risky, or likely to need a handoff.",
      ],
      baseHelpLinks(),
      baseDetail,
    );
  }, [
    actionLoading,
    inventoryQuery.isFetching,
    inventoryState.kind,
    operators.length,
    resultState.kind,
    rosterQuery.isFetching,
    rosterQuery.isPending,
    rosterState.kind,
    validationIssues,
  ]);
  const paletteSearchResults = commandPaletteSearchQuery.data ?? [];

  const paletteAppAndGlossaryEntries = useMemo<CommandPaletteItem[]>(
    () =>
      paletteStaticEntries.map((item) => ({
        ...item,
        onSelect: () => {
          if (item.href) {
            openHref(item.href, item.newTab);
          }
        },
        searchValue: buildPaletteSearchValue(item),
      })),
    [],
  );

  const palettePageEntries = useMemo<CommandPaletteItem[]>(
    () => [
      {
        id: "page:roster",
        label: "Roster",
        description: "Jump to the AG Grid roster and focus the quick filter.",
        lane: "observe",
        kind: "page",
        keywords: ["operators", "ag grid", "quick filter", "roster"],
        canFavorite: true,
        onSelect: () => focusElementById("operator-quick-filter", '[data-tour-target="roster-panel"]'),
        searchValue: "Roster operators ag grid quick filter observe",
      },
      {
        id: "page:notes",
        label: "Rich Notes",
        description: "Jump to the bounded rich-text notes workspace for the selected operator.",
        lane: "change",
        kind: "page",
        keywords: ["notes", "markdown", "tiptap", "editor"],
        canFavorite: true,
        onSelect: () => focusElementById("operator-notes-markdown", ".notesWorkspace"),
        searchValue: "Rich Notes markdown editor tiptap notes workspace change",
      },
      {
        id: "page:onboard",
        label: "Onboard Operator",
        description: "Jump to the schema-first onboarding form and focus the name field.",
        lane: "change",
        kind: "page",
        keywords: ["onboard", "create operator", "access", "form"],
        canFavorite: true,
        onSelect: () => focusElementById("onboard-name", '[data-tour-target="onboard-form"]'),
        searchValue: "Onboard Operator create operator schema form change",
      },
      {
        id: "page:offboard",
        label: "Off-board Operator",
        description: "Jump to the governed off-boarding form and focus the operator selector.",
        lane: "recover",
        kind: "page",
        keywords: ["offboard", "disable operator", "revoke access"],
        canFavorite: true,
        onSelect: () => focusElementById("offboard-operator", '[data-tour-target="offboard-form"]'),
        searchValue: "Off-board Operator disable revoke access recover",
      },
      {
        id: "page:reconcile",
        label: "Reconcile Roster",
        description: "Jump to the reconciliation form and focus the scope selector.",
        lane: "change",
        kind: "page",
        keywords: ["reconcile", "sync operators", "roster"],
        canFavorite: true,
        onSelect: () => focusElementById("sync-operator"),
        searchValue: "Reconcile Roster sync operators change",
      },
      {
        id: "page:inventory",
        label: "Selected Operator Inventory",
        description: "Jump to the live inventory panel for the currently selected operator.",
        lane: "observe",
        kind: "page",
        keywords: ["inventory", "selected operator", "access report"],
        canFavorite: true,
        onSelect: () => document.querySelector('[data-tour-target="inventory-panel"]')?.scrollIntoView({ behavior: "smooth", block: "start" }),
        searchValue: "Selected Operator Inventory observe access report",
      },
    ],
    [],
  );

  const paletteQuickActionEntries = useMemo<CommandPaletteItem[]>(() => {
    const items: CommandPaletteItem[] = [
      {
        id: "quick:refresh-roster",
        label: "Refresh Roster",
        description: "Re-run the live operator roster query without leaving the palette.",
        lane: "observe",
        kind: "quick_action",
        keywords: ["refresh", "roster", "query"],
        onSelect: () => {
          void rosterQuery.refetch();
        },
        searchValue: "Refresh Roster observe query refresh",
      },
      {
        id: "quick:refresh-inventory",
        label: "Refresh Inventory",
        description: "Refresh the selected operator inventory panel.",
        lane: "observe",
        kind: "quick_action",
        keywords: ["refresh", "inventory", "selected operator"],
        onSelect: () => {
          if (selectedOperatorId) {
            void inventoryQuery.refetch();
          }
        },
        searchValue: "Refresh Inventory observe selected operator",
      },
      {
        id: "quick:tour-first-run",
        label: "Start First-Run Tour",
        description: "Launch the guided onboarding walkthrough for new operators.",
        lane: "start",
        kind: "quick_action",
        keywords: ["tour", "first run", "guided onboarding"],
        onSelect: () => launchTour("first_run"),
        searchValue: "Start First-Run Tour onboarding start guided",
      },
      {
        id: "quick:tour-onboard-privileged",
        label: "Start Onboard Admin Or Operator Tour",
        description: "Launch the guided onboarding path for privileged operators.",
        lane: "change",
        kind: "quick_action",
        keywords: ["tour", "admin", "operator", "onboard"],
        onSelect: () => launchTour("onboard_privileged"),
        searchValue: "Start Onboard Admin Or Operator Tour change guided onboarding",
      },
      {
        id: "quick:tour-onboard-viewer",
        label: "Start Onboard Viewer Tour",
        description: "Launch the guided onboarding path for a read-only viewer.",
        lane: "start",
        kind: "quick_action",
        keywords: ["tour", "viewer", "onboard"],
        onSelect: () => launchTour("onboard_viewer"),
        searchValue: "Start Onboard Viewer Tour start guided onboarding viewer",
      },
      {
        id: "quick:tour-offboard",
        label: "Start Off-board Tour",
        description: "Launch the guided off-boarding walkthrough.",
        lane: "recover",
        kind: "quick_action",
        keywords: ["tour", "offboard", "revoke", "disable"],
        onSelect: () => launchTour("offboard"),
        searchValue: "Start Off-board Tour recover offboard guided",
      },
      {
        id: "quick:tour-inventory",
        label: "Start Inventory Review Tour",
        description: "Launch the guided inventory review path for the selected operator.",
        lane: "observe",
        kind: "quick_action",
        keywords: ["tour", "inventory", "review"],
        onSelect: () => launchTour("inventory"),
        searchValue: "Start Inventory Review Tour observe guided review",
      },
    ];

    if (canResumeTour && tourProgress.lastIntent) {
      items.unshift({
        id: "quick:tour-resume",
        label: `Resume ${tourIntentLabel(tourProgress.lastIntent)}`,
        description: "Resume the most recently dismissed guided walkthrough in this browser.",
        lane: "start",
        kind: "quick_action",
        keywords: ["resume", "tour", "guided onboarding"],
        onSelect: () => launchTour(tourProgress.lastIntent!, { resume: true }),
        searchValue: `Resume ${tourIntentLabel(tourProgress.lastIntent)} start guided tour`,
      });
    }

    return items;
  }, [
    canResumeTour,
    inventoryQuery,
    launchTour,
    rosterQuery,
    selectedOperatorId,
    tourProgress.lastIntent,
  ]);

  const paletteOperatorEntries = useMemo<CommandPaletteItem[]>(
    () =>
      operators.map((operator) => ({
        id: `operator:${operator.id}`,
        label: operator.name,
        description: `${operator.role} • ${operator.status} • ${operator.email}`,
        lane: operator.status === "inactive" ? "recover" : "observe",
        kind: "operator",
        keywords: [
          operator.id,
          operator.email,
          operator.role,
          operator.status,
          operator.keycloak_username,
          ...operator.realm_roles,
          ...operator.groups,
        ],
        canFavorite: true,
        onSelect: () => {
          if (selectOperator(operator.id)) {
            focusElementById("operator-quick-filter", '[data-tour-target="roster-panel"]');
          }
        },
        searchValue: [
          operator.name,
          operator.id,
          operator.email,
          operator.role,
          operator.status,
          operator.keycloak_username,
          operator.realm_roles.join(" "),
          operator.groups.join(" "),
        ]
          .join(" ")
          .trim(),
      })),
    [operators, notesDirty, selectedOperatorId],
  );

  const paletteDocsEntries = useMemo<CommandPaletteItem[]>(
    () =>
      paletteSearchResults.map((result) => ({
        id: result.id,
        label: result.title,
        description: result.description || `Open the matching ${paletteKindLabels[result.kind]}.`,
        lane: result.lane,
        kind: result.kind,
        href: result.href,
        keywords: result.keywords,
        newTab: true,
        onSelect: () => openHref(result.href, true),
        searchValue: buildPaletteSearchValue({
          id: result.id,
          label: result.title,
          description: result.description,
          lane: result.lane,
          kind: result.kind,
          href: result.href,
          keywords: result.keywords,
          newTab: true,
        }),
      })),
    [paletteSearchResults],
  );

  const paletteEntryIndex = useMemo(() => {
    const entries = [
      ...paletteAppAndGlossaryEntries,
      ...palettePageEntries,
      ...paletteQuickActionEntries,
      ...paletteOperatorEntries,
    ];
    return new Map(entries.map((item) => [item.id, item] as const));
  }, [
    paletteAppAndGlossaryEntries,
    paletteOperatorEntries,
    palettePageEntries,
    paletteQuickActionEntries,
  ]);

  const paletteFavoriteEntries = useMemo(
    () => paletteState.favoriteIds.map((itemId) => paletteEntryIndex.get(itemId)).filter(Boolean) as CommandPaletteItem[],
    [paletteEntryIndex, paletteState.favoriteIds],
  );

  const paletteRecentEntries = useMemo(() => {
    const favoriteIds = new Set(paletteState.favoriteIds);
    return paletteState.recentIds
      .filter((itemId) => !favoriteIds.has(itemId))
      .map((itemId) => paletteEntryIndex.get(itemId))
      .filter(Boolean) as CommandPaletteItem[];
  }, [paletteEntryIndex, paletteState.favoriteIds, paletteState.recentIds]);

  const paletteSections = useMemo<CommandPaletteSection[]>(() => {
    const excludedIds = new Set([
      ...paletteFavoriteEntries.map((item) => item.id),
      ...paletteRecentEntries.map((item) => item.id),
    ]);
    const applicationEntries = paletteAppAndGlossaryEntries.filter(
      (item) => item.kind === "application" && !excludedIds.has(item.id),
    );
    const glossaryEntries = paletteAppAndGlossaryEntries.filter((item) => item.kind === "glossary");
    const pageEntries = palettePageEntries.filter((item) => !excludedIds.has(item.id));
    const operatorEntries = paletteOperatorEntries.filter((item) => !excludedIds.has(item.id));

    return [
      { id: "favorites", label: "Favorites", items: paletteFavoriteEntries },
      { id: "recent", label: "Recent", items: paletteRecentEntries },
      { id: "applications", label: "Applications", items: applicationEntries },
      { id: "pages", label: "Pages", items: pageEntries },
      { id: "operators", label: "Operators", items: operatorEntries },
      { id: "docs", label: "Docs And Runbooks", items: paletteDocsEntries },
      { id: "glossary", label: "Glossary", items: glossaryEntries },
      { id: "actions", label: "Quick Actions", items: paletteQuickActionEntries },
    ].filter((section) => section.items.length > 0);
  }, [
    paletteAppAndGlossaryEntries,
    paletteDocsEntries,
    paletteFavoriteEntries,
    palettePageEntries,
    paletteQuickActionEntries,
    paletteRecentEntries,
    paletteOperatorEntries,
  ]);

  const checklistCompletedCount = CHECKLIST_ITEMS.filter((item) => journeyProgress.checklist[item.id]).length;
  const checklistCompletionRate = Number(
    scorecardsQuery.data?.scorecards.onboarding_checklist_completion.completion_rate ?? 0,
  );
  const medianSafeAction = formatDurationSeconds(
    scorecardsQuery.data?.scorecards.time_to_first_safe_action.median_seconds,
  );
  const resumableCompletionRate = Number(
    scorecardsQuery.data?.scorecards.resumable_task_completion.completion_rate ?? 0,
  );
  const routePageviews = scorecardsQuery.data?.route_aggregates.pageviews ?? {};

  return (
    <div className="shell">
      {paletteOpen ? (
        <div className="commandPaletteModal" onMouseDown={closePalette}>
          <div className="commandPaletteShell" onMouseDown={(event) => event.stopPropagation()}>
            <Command
              loop
              label="Operator access command palette"
              className="commandPalette"
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  event.preventDefault();
                  closePalette();
                }
              }}
            >
              <div className="commandPaletteHeader">
                <div>
                  <p className="commandPaletteEyebrow">Global Command Palette</p>
                  <h2>Universal open dialog for operators, runbooks, glossary, and safe quick actions</h2>
                </div>
                <button className="commandPaletteClose" type="button" onClick={closePalette} aria-label="Close command palette">
                  Esc
                </button>
              </div>
              <div className="commandPaletteInputRow">
                <Command.Input
                  autoFocus
                  value={paletteQuery}
                  onValueChange={setPaletteQuery}
                  placeholder="Search operators, runbooks, ADRs, glossary terms, and actions"
                  className="commandPaletteInput"
                />
                <span className="commandPaletteShortcut">Ctrl/Cmd+K</span>
              </div>
              <Command.List className="commandPaletteList">
                <Command.Empty className="commandPaletteEmpty">
                  No matching destinations yet. Try an operator name, a runbook term, or an action like
                  &nbsp;`refresh roster`.
                </Command.Empty>
                {commandPaletteSearchQuery.isFetching ? (
                  <div className="commandPaletteStatus">Searching ADRs and runbooks through the repo search fabric…</div>
                ) : null}
                {commandPaletteSearchQuery.isError ? (
                  <div className="commandPaletteStatus commandPaletteStatusWarning">
                    Docs search is temporarily degraded. Local actions, operators, and saved destinations still work.
                  </div>
                ) : null}
                {paletteSections.map((section) => (
                  <Command.Group key={section.id} heading={section.label} className="commandPaletteGroup">
                    {section.items.map((item) => {
                      const isFavorite = paletteState.favoriteIds.includes(item.id);
                      return (
                        <Command.Item
                          key={item.id}
                          value={item.searchValue}
                          keywords={item.keywords}
                          className="commandPaletteItem"
                          onSelect={() => runPaletteItem(item)}
                        >
                          <div className="commandPaletteItemCopy">
                            <div className="commandPaletteItemMeta">
                              <span className="commandPaletteBadge highlighted">{paletteLaneLabels[item.lane]}</span>
                              <span className="commandPaletteBadge">{paletteKindLabels[item.kind]}</span>
                            </div>
                            <span className="commandPaletteItemLabel">{item.label}</span>
                            <span className="commandPaletteItemDescription">{item.description}</span>
                          </div>
                          {item.canFavorite ? (
                            <button
                              type="button"
                              className="commandPaletteFavorite"
                              aria-label={`${isFavorite ? "Remove" : "Add"} ${item.label} ${isFavorite ? "from" : "to"} favorites`}
                              onMouseDown={(event) => {
                                event.preventDefault();
                                event.stopPropagation();
                                handlePaletteFavoriteToggle(item.id);
                              }}
                            >
                              {isFavorite ? "★" : "☆"}
                            </button>
                          ) : null}
                        </Command.Item>
                      );
                    })}
                  </Command.Group>
                ))}
              </Command.List>
              <div className="commandPaletteFooter">
                <span>Recent destinations stay local to this browser session family.</span>
                <span>Destructive work still routes into the full governed forms.</span>
              </div>
            </Command>
          </div>
        </div>
      ) : null}
      <section className="hero">
        <div className="heroCard">
          <h1>Operator Access Admin</h1>
          <p>
            Browser-first access control for ADR 0108. This console combines schema-first forms,
            the data-dense AG Grid roster, task-specific guided tours, and bounded rich notes while
            keeping every mutation on the same repo-managed backend path.
          </p>
          <p className="muted">Mutations now invalidate TanStack Query cache entries instead of forcing a full-page refresh.</p>
          <div className="heroActions">
            <button className="button" type="button" onClick={() => setPaletteOpen(true)}>
              Open Command Palette
            </button>
            <span className="heroShortcut">Ctrl/Cmd+K</span>
            <span className="muted">
              Search operators, pages, runbooks, ADRs, glossary terms, and safe quick actions from one universal open dialog.
            </span>
          </div>
        </div>
        <div className="heroStats">
          <div className="heroCard stat">
            <span className="statLabel">Total Operators</span>
            <span className="statValue">{rosterQuery.data?.operator_count ?? "…"}</span>
          </div>
          <div className="heroCard stat">
            <span className="statLabel">Active</span>
            <span className="statValue">{rosterQuery.data?.active_count ?? "…"}</span>
          </div>
          <div className="heroCard stat">
            <span className="statLabel">Inactive</span>
            <span className="statValue">{rosterQuery.data?.inactive_count ?? "…"}</span>
          </div>
          <div className="heroCard stat">
            <span className="statLabel">Checklist Completion</span>
            <span className="statValue">{checklistCompletionRate.toFixed(1)}%</span>
          </div>
          <div className="heroCard stat">
            <span className="statLabel">Median Safe Action</span>
            <span className="statValue">{medianSafeAction}</span>
          </div>
          <div className="heroCard stat">
            <span className="statLabel">Resume Success</span>
            <span className="statValue">{resumableCompletionRate.toFixed(1)}%</span>
          </div>
        </div>
      </section>

      <section className="heroCard tourCard" data-tour-target="tour-launcher">
        <div className="tourCardHeader">
          <div>
            <span className="eyebrow">Guided Onboarding</span>
            <h2>Task-specific Shepherd tours for first-run operators</h2>
            <p>
              Start a walkthrough for the exact workflow you need. Tours are dismissible, resumable in this browser,
              and linked to the canonical runbooks rather than duplicating policy in UI copy.
            </p>
          </div>
          <div className="tourMeta">
            <span
              className={`pill ${
                tourRunning ? "pillActive" : tourProgress.lastOutcome === "dismissed" ? "pillPaused" : "pillRole"
              }`}
            >
              {tourStatusLabel}
            </span>
            {tourProgress.lastIntent ? <span className="muted">Last tour: {tourIntentLabel(tourProgress.lastIntent)}</span> : null}
            {lastTourTimestamp ? <span className="muted">Updated {formatDate(lastTourTimestamp)}</span> : null}
          </div>
        </div>
        <div className="tourActions">
          <button className="button" onClick={() => launchTour("first_run")} disabled={tourRunning}>
            Start First-Run Tour
          </button>
          {canResumeTour && tourProgress.lastIntent ? (
            <button className="buttonGhost" onClick={() => launchTour(tourProgress.lastIntent!, { resume: true })} disabled={tourRunning}>
              Resume {tourIntentLabel(tourProgress.lastIntent)}
            </button>
          ) : null}
          <button className="buttonGhost" onClick={() => launchTour("onboard_privileged")} disabled={tourRunning}>
            Onboard Admin Or Operator
          </button>
          <button className="buttonGhost" onClick={() => launchTour("onboard_viewer")} disabled={tourRunning}>
            Onboard Viewer
          </button>
          <button className="buttonGhost" onClick={() => launchTour("offboard")} disabled={tourRunning}>
            Off-board Operator
          </button>
          <button className="buttonGhost" onClick={() => launchTour("inventory")} disabled={tourRunning}>
            Review Inventory
          </button>
          <button className="buttonGhost" onClick={() => openHelpDrawer("guided_onboarding")} disabled={tourRunning}>
            Open Help Drawer
          </button>
        </div>
        <p className="tourFootnote">
          Need the full operating procedure?{" "}
          <a className="inlineLink" href="https://docs.example.com/runbooks/windmill-operator-access-admin/" target="_blank" rel="noreferrer">
            Open the operator admin runbook
          </a>
          .
        </p>
      </section>

      {activeAlert ? (
        <section className="banner bannerError alertBanner">
          <div>
            <strong>Journey alert:</strong> {activeAlert.message}
          </div>
          <div className="toolbar">
            <button className="buttonGhost" type="button" onClick={acknowledgeActiveAlert}>
              {activeAlert.acknowledgedAt ? "Acknowledged" : "Acknowledge"}
            </button>
            <button className="buttonGhost" type="button" onClick={() => openHelpDrawer("alert_recovery")}>
              Open Help Drawer
            </button>
            <button className="buttonGhost" type="button" onClick={() => void rosterQuery.refetch()}>
              Retry Roster
            </button>
          </div>
        </section>
      ) : null}

      <StateGuidanceCard state={pageState} eyebrow="ADR 0315 Page Guidance" />

      <div className="layout">
        <div className="mainColumn">
          <section className="panel" data-tour-target="roster-panel">
            <div className="panelHeader">
              <div>
                <h2>Roster</h2>
                <p>Current human operators from the repo-authoritative `config/operators.yaml` roster.</p>
              </div>
              <div className="toolbar">
                <button
                  className="buttonGhost"
                  onClick={() => void rosterQuery.refetch()}
                  disabled={rosterQuery.isFetching || actionLoading}
                >
                  {rosterQuery.isFetching ? "Refreshing…" : "Refresh"}
                </button>
              </div>
            </div>

            <div className="statusRow">
              <span className={`pill ${rosterFeedback.toneClass}`}>{rosterFeedback.label}</span>
              <span className="statusMeta">{rosterFeedback.detail}</span>
            </div>

            {rosterState.kind !== "success" ? <StateGuidanceCard state={rosterState} compact eyebrow="Roster State" /> : null}

            {rosterQuery.error ? <div className="banner bannerError">{getErrorMessage(rosterQuery.error)}</div> : null}
            {!rosterQuery.error ? (
              <div className="banner bannerInfo">
                Bootstrap passwords are returned once on successful onboarding. Store them securely and expect the
                new operator to rotate them and enroll TOTP at first sign-in.
              </div>
            ) : null}

            <div className="tableWrap">
              <div className="gridControls">
                <label className="gridSearch">
                  <span className="gridSearchLabel">Quick Filter</span>
                  <input
                    id="operator-quick-filter"
                    value={quickFilterText}
                    onChange={(event) => setQuickFilterText(event.target.value)}
                    placeholder="Search by operator, role, group, status, or notes"
                  />
                </label>
                <div className="toolbar">
                  <button
                    className="buttonGhost"
                    onClick={() => setQuickFilterText("")}
                    disabled={!quickFilterText}
                    type="button"
                  >
                    Clear Search
                  </button>
                  <button
                    className="buttonGhost"
                    onClick={() => {
                      gridApiRef.current?.resetColumnState();
                      gridApiRef.current?.setFilterModel(null);
                    }}
                    disabled={!operators.length}
                    type="button"
                  >
                    Reset Columns
                  </button>
                </div>
              </div>

              <div className="gridSummary">
                <span className="pill pillRole">
                  Showing {displayedOperatorCount} of {operators.length}
                </span>
                <span className="muted">
                  Sort, filter, pin, or resize columns. Keyboard selection works with arrow keys plus space.
                </span>
              </div>

              <div className="gridHost">
                <AgGridReact<OperatorRecord>
                  theme={operatorGridTheme}
                  rowData={operators}
                  columnDefs={rosterColumns}
                  defaultColDef={defaultColDef}
                  rowSelection={rosterRowSelection}
                  quickFilterText={deferredQuickFilterText}
                  includeHiddenColumnsInQuickFilter={true}
                  cacheQuickFilter={true}
                  pagination={true}
                  paginationPageSize={10}
                  paginationPageSizeSelector={[10, 25, 50]}
                  animateRows={true}
                  rowHeight={74}
                  headerHeight={50}
                  getRowId={({ data }) => data.id}
                  overlayNoRowsTemplate={
                    rosterQuery.isPending
                      ? '<span class="ag-overlay-loading-center">Loading operator roster…</span>'
                      : "No operators found in the roster."
                  }
                  onGridReady={handleGridReady}
                  onModelUpdated={handleGridModelUpdated}
                  onSelectionChanged={handleGridSelectionChanged}
                />
              </div>
            </div>
          </section>

          <section className="panel">
            <div className="panelHeader">
              <div>
                <h2>Rich Notes</h2>
                <p>
                  ADR 0241 bounded knowledge editor powered by Tiptap. Notes stay markdown-backed in
                  `config/operators.yaml` while the rich editor handles headings, task items, tables, links,
                  and mention-style person references.
                </p>
              </div>
              <div className="toolbar">
                <button
                  className="buttonGhost"
                  type="button"
                  onClick={() => setNotesMarkdown(selectedOperatorNotes)}
                  disabled={!notesDirty || actionLoading}
                >
                  Reset
                </button>
                <button
                  className="button"
                  type="button"
                  onClick={() => void handleSaveNotes()}
                  disabled={!selectedOperatorId || !notesDirty || actionLoading}
                >
                  {notesMutation.isPending ? "Saving…" : "Save Notes"}
                </button>
              </div>
            </div>

            <StateGuidanceCard state={notesState} compact eyebrow="Rich Notes State" />

            {selectedOperator ? (
              <>
                <div className="inventoryMeta noteMeta">
                  <span className="pill pillRole">{selectedOperator.name}</span>
                  <span className={`pill ${pillToneClass(selectedOperator.status)}`}>{selectedOperator.status}</span>
                  <span className="pill">{selectedOperator.role}</span>
                  <span className="pill">{selectedOperator.keycloak_username || "no username"}</span>
                  <span className="pill">{selectedOperator.notes ? "Notes present" : "No saved notes"}</span>
                  <span className="pill">Reviewed {formatDate(selectedOperator.last_reviewed_at)}</span>
                </div>

                <div className="editorToolbar">
                  <div className="toolbarGroup">
                    <ToolbarButton label="H1" onClick={() => editor?.chain().focus().toggleHeading({ level: 1 }).run()} active={editor?.isActive("heading", { level: 1 }) ?? false} disabled={!editor} />
                    <ToolbarButton label="H2" onClick={() => editor?.chain().focus().toggleHeading({ level: 2 }).run()} active={editor?.isActive("heading", { level: 2 }) ?? false} disabled={!editor} />
                    <ToolbarButton label="Bold" onClick={() => editor?.chain().focus().toggleBold().run()} active={editor?.isActive("bold") ?? false} disabled={!editor} />
                    <ToolbarButton label="Italic" onClick={() => editor?.chain().focus().toggleItalic().run()} active={editor?.isActive("italic") ?? false} disabled={!editor} />
                  </div>
                  <div className="toolbarGroup">
                    <ToolbarButton label="Bullets" onClick={() => editor?.chain().focus().toggleBulletList().run()} active={editor?.isActive("bulletList") ?? false} disabled={!editor} />
                    <ToolbarButton label="Ordered" onClick={() => editor?.chain().focus().toggleOrderedList().run()} active={editor?.isActive("orderedList") ?? false} disabled={!editor} />
                    <ToolbarButton label="Tasks" onClick={() => editor?.chain().focus().toggleTaskList().run()} active={editor?.isActive("taskList") ?? false} disabled={!editor} />
                    <ToolbarButton label="Code" onClick={() => editor?.chain().focus().toggleCodeBlock().run()} active={editor?.isActive("codeBlock") ?? false} disabled={!editor} />
                    <ToolbarButton label="Link" onClick={toggleLink} active={editor?.isActive("link") ?? false} disabled={!editor} />
                    <ToolbarButton label="Table" onClick={() => editor?.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()} disabled={!editor} />
                  </div>
                  <div className="toolbarGroup toolbarGroupFill">
                    <select
                      className="toolbarSelect"
                      value={mentionTarget}
                      onChange={(event) => setMentionTarget(event.target.value)}
                    >
                      <option value="">Insert person mention...</option>
                      {operators.map((operator) => (
                        <option key={operator.id} value={operator.id}>
                          {operator.name}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="toolbarButton"
                      onClick={() => insertOperatorMention(mentionTarget)}
                      disabled={!editor || !mentionTarget}
                    >
                      Mention
                    </button>
                  </div>
                </div>

                <div className="notesWorkspace">
                  <div className="notesPane">
                    <div className="workspaceHeader">
                      <h3>Rich Editor</h3>
                      <p>Inline formatting is rendered live while markdown remains the stored source of truth.</p>
                    </div>
                    <div className="editorSurface">
                      <EditorContent editor={editor} />
                    </div>
                  </div>

                  <div className="sourcePane">
                    <div className="workspaceHeader">
                      <h3>Markdown Source</h3>
                      <p>Paste or edit markdown directly to import and export the same note content.</p>
                    </div>
                    <textarea
                      id="operator-notes-markdown"
                      className="markdownTextarea"
                      value={notesMarkdown}
                      onChange={(event) => setNotesMarkdown(event.target.value)}
                      placeholder={"## Shift handoff\n\n- [ ] Review alerts\n- Link relevant runbooks\n- Mention @operator-id"}
                    />
                  </div>
                </div>

                <div className="editorFooter">
                  <span className="muted">Stored note length: {notesMarkdown.trim().length} character(s)</span>
                  <span className={`pill ${notesDirty ? "pillWarning" : "pillSuccess"}`}>
                    {notesDirty ? "Unsaved changes" : "Saved"}
                  </span>
                </div>
              </>
            ) : null}
          </section>
        </div>

        <aside className="sidebar">
          <section className="panel scorecardPanel">
            <div className="panelHeader">
              <div>
                <h3>Onboarding Success Scorecard</h3>
                <p>
                  Privacy-preserving ADR 0316 scorecards combine browser milestones, governed worker receipts,
                  Plausible route aliases, and Glitchtip failure signals.
                </p>
              </div>
              <div className="toolbar">
                <button
                  className="buttonGhost"
                  type="button"
                  onClick={() => void scorecardsQuery.refetch()}
                  disabled={scorecardsQuery.isFetching}
                >
                  {scorecardsQuery.isFetching ? "Refreshing…" : "Refresh"}
                </button>
              </div>
            </div>

            <div className="statusRow">
              <span className={`pill ${scorecardsFeedback.toneClass}`}>{scorecardsFeedback.label}</span>
              <span className="statusMeta">{scorecardsFeedback.detail}</span>
            </div>

            <div className="scorecardSummary">
              <div className="scorecardMetric">
                <span className="statLabel">This Browser</span>
                <strong>
                  {checklistCompletedCount}/{CHECKLIST_ITEMS.length}
                </strong>
              </div>
              <div className="scorecardMetric">
                <span className="statLabel">Visitors</span>
                <strong>{scorecardsQuery.data?.population.visitors ?? 0}</strong>
              </div>
              <div className="scorecardMetric">
                <span className="statLabel">Glitchtip Signals</span>
                <strong>{scorecardsQuery.data?.failure_signals.glitchtip_events ?? 0}</strong>
              </div>
            </div>

            <div className="checklistList">
              {CHECKLIST_ITEMS.map((item) => {
                const completedAt = journeyProgress.checklist[item.id];
                return (
                  <div key={item.id} className="checklistItem">
                    <div>
                      <strong>{item.title}</strong>
                      <p>{item.hint}</p>
                    </div>
                    <div className="checklistMeta">
                      <span className={`pill ${completedAt ? "pillSuccess" : "pillWarning"}`}>
                        {completedAt ? "Complete" : "Pending"}
                      </span>
                      <span className="muted">{completedAt ? formatDate(completedAt) : "Not yet completed"}</span>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="scorecardGrid">
              <div className="scorecardMetric">
                <span className="statLabel">Search Success</span>
                <strong>
                  {Number(scorecardsQuery.data?.scorecards.search_to_destination_success.success_rate ?? 0).toFixed(1)}%
                </strong>
              </div>
              <div className="scorecardMetric">
                <span className="statLabel">Alert Resolution</span>
                <strong>
                  {formatDurationSeconds(scorecardsQuery.data?.scorecards.alert_handoffs.median_resolution_seconds)}
                </strong>
              </div>
              <div className="scorecardMetric">
                <span className="statLabel">Help To Success</span>
                <strong>
                  {Number(scorecardsQuery.data?.scorecards.help_to_successful_recovery.success_rate ?? 0).toFixed(1)}%
                </strong>
              </div>
            </div>

            <div className="routeAggregateList">
              <div className="routeAggregateItem">
                <span className="muted">Start route</span>
                <strong>{routePageviews["/journeys/operator-access-admin/start"] ?? 0}</strong>
              </div>
              <div className="routeAggregateItem">
                <span className="muted">Search route</span>
                <strong>{routePageviews["/journeys/operator-access-admin/search"] ?? 0}</strong>
              </div>
              <div className="routeAggregateItem">
                <span className="muted">Help route</span>
                <strong>{routePageviews["/journeys/operator-access-admin/help"] ?? 0}</strong>
              </div>
            </div>
          </section>

          <section className={`panel helpDrawer ${helpDrawerOpen ? "isOpen" : ""}`} data-tour-target="help-drawer">
            <div className="panelHeader">
              <div>
                <h3>Contextual Help Drawer</h3>
                <p>
                  Use guided recovery paths instead of guessing when onboarding stalls, an alert appears, or you
                  need the safe next action fast.
                </p>
              </div>
              <div className="toolbar">
                <button
                  className="buttonGhost"
                  type="button"
                  onClick={() => (helpDrawerOpen ? setHelpDrawerOpen(false) : openHelpDrawer("manual_open"))}
                >
                  {helpDrawerOpen ? "Close" : "Open"}
                </button>
              </div>
            </div>

            {helpDrawerOpen ? (
              <div className="helpDrawerBody">
                <div className="helpActionList">
                  <button className="button" type="button" onClick={() => launchTour("first_run")}>
                    Start First-Run Tour
                  </button>
                  <button className="buttonGhost" type="button" onClick={() => void inventoryQuery.refetch()} disabled={!selectedOperatorId}>
                    Refresh Inventory
                  </button>
                  <button className="buttonGhost" type="button" onClick={() => void rosterQuery.refetch()}>
                    Refresh Roster
                  </button>
                </div>
                <div className="helpLinks">
                  <a className="inlineLink" href="https://docs.example.com/runbooks/windmill-operator-access-admin/" target="_blank" rel="noreferrer">
                    Operator admin runbook
                  </a>
                  <a className="inlineLink" href="https://docs.example.com/runbooks/operator-onboarding/" target="_blank" rel="noreferrer">
                    Operator onboarding runbook
                  </a>
                  <a className="inlineLink" href="https://docs.example.com/runbooks/operator-offboarding/" target="_blank" rel="noreferrer">
                    Operator off-boarding runbook
                  </a>
                </div>
                <p className="muted">
                  Help success is counted only when a later inventory refresh, guided tour completion, or governed
                  mutation finishes successfully.
                </p>
              </div>
            ) : (
              <p className="muted">Open the drawer to start a recoverable help flow without leaving the current page.</p>
            )}
          </section>

          <div className="forms">
            <form className="panel" onSubmit={handleOnboardSubmit} noValidate data-tour-target="onboard-form">
              <div className="panelHeader">
                <div>
                  <h3>Onboard Operator</h3>
                  <p>Create a new human operator through the governed ADR 0108 workflow.</p>
                </div>
              </div>
              <fieldset className="formBody" disabled={actionLoading}>
                <FormStatus
                  isSubmitting={onboardForm.formState.isSubmitting}
                  isDirty={onboardForm.formState.isDirty}
                  submitCount={onboardForm.formState.submitCount}
                  errorCount={onboardErrorCount}
                  idleMessage="Schema validation mirrors the governed onboarding payload."
                  helpHref={RUNBOOK_URLS.operatorOnboarding}
                  helpLabel="Open operator onboarding runbook"
                />
                <div className="formGrid">
                  <FieldShell
                    htmlFor="onboard-name"
                    label="Name"
                    hint="Full human-readable operator name."
                    error={onboardForm.formState.errors.name?.message}
                    touched={onboardForm.formState.touchedFields.name}
                    required
                  >
                    <input
                      id="onboard-name"
                      {...onboardForm.register("name")}
                      aria-invalid={Boolean(onboardForm.formState.errors.name)}
                    />
                  </FieldShell>

                  <FieldShell
                    htmlFor="onboard-email"
                    label="Email"
                    hint="Used for the operator roster and login workflows."
                    error={onboardForm.formState.errors.email?.message}
                    touched={onboardForm.formState.touchedFields.email}
                    required
                  >
                    <input
                      id="onboard-email"
                      type="email"
                      {...onboardForm.register("email")}
                      aria-invalid={Boolean(onboardForm.formState.errors.email)}
                    />
                  </FieldShell>

                  <FieldShell
                    htmlFor="onboard-role"
                    label="Role"
                    hint="Controls SSH and privilege expectations."
                    error={onboardForm.formState.errors.role?.message}
                    touched={onboardForm.formState.touchedFields.role}
                    required
                    tourTarget="role-field"
                  >
                    <select
                      id="onboard-role"
                      {...onboardForm.register("role")}
                      aria-invalid={Boolean(onboardForm.formState.errors.role)}
                    >
                      <option value="admin">admin</option>
                      <option value="operator">operator</option>
                      <option value="viewer">viewer</option>
                    </select>
                  </FieldShell>

                  <FieldShell
                    htmlFor="onboard-operator-id"
                    label="Operator ID"
                    hint="Optional slug override such as alice-example."
                    error={onboardForm.formState.errors.operator_id?.message}
                    touched={onboardForm.formState.touchedFields.operator_id}
                  >
                    <input
                      id="onboard-operator-id"
                      {...onboardForm.register("operator_id")}
                      aria-invalid={Boolean(onboardForm.formState.errors.operator_id)}
                      placeholder="optional slug"
                    />
                  </FieldShell>

                  <FieldShell
                    htmlFor="onboard-keycloak-username"
                    label="Keycloak Username"
                    hint="Optional username override for Keycloak."
                    error={onboardForm.formState.errors.keycloak_username?.message}
                    touched={onboardForm.formState.touchedFields.keycloak_username}
                  >
                    <input
                      id="onboard-keycloak-username"
                      {...onboardForm.register("keycloak_username")}
                      aria-invalid={Boolean(onboardForm.formState.errors.keycloak_username)}
                      placeholder="optional username override"
                    />
                  </FieldShell>

                  <FieldShell
                    htmlFor="onboard-tailscale-login-email"
                    label="Tailscale Login Email"
                    hint="Optional override for the Tailscale identity."
                    error={onboardForm.formState.errors.tailscale_login_email?.message}
                    touched={onboardForm.formState.touchedFields.tailscale_login_email}
                  >
                    <input
                      id="onboard-tailscale-login-email"
                      type="email"
                      {...onboardForm.register("tailscale_login_email")}
                      aria-invalid={Boolean(onboardForm.formState.errors.tailscale_login_email)}
                      placeholder="optional override"
                    />
                  </FieldShell>

                  <FieldShell
                    htmlFor="onboard-ssh-key"
                    label="SSH Public Key"
                    hint={sshRequired ? "Admin and operator accounts require a public key." : "Optional for viewer accounts."}
                    error={onboardForm.formState.errors.ssh_key?.message}
                    touched={onboardForm.formState.touchedFields.ssh_key}
                    required={sshRequired}
                    stretch
                    tourTarget="ssh-key-field"
                  >
                    <textarea
                      id="onboard-ssh-key"
                      {...onboardForm.register("ssh_key")}
                      aria-invalid={Boolean(onboardForm.formState.errors.ssh_key)}
                      placeholder="ssh-ed25519 AAAA..."
                    />
                  </FieldShell>

                  <FieldShell
                    htmlFor="onboard-device-name"
                    label="Tailscale Device Name"
                    hint="Optional label for the expected device."
                    error={onboardForm.formState.errors.tailscale_device_name?.message}
                    touched={onboardForm.formState.touchedFields.tailscale_device_name}
                    stretch
                  >
                    <input
                      id="onboard-device-name"
                      {...onboardForm.register("tailscale_device_name")}
                      aria-invalid={Boolean(onboardForm.formState.errors.tailscale_device_name)}
                      placeholder="optional device label"
                    />
                  </FieldShell>
                </div>
                <label className="checkboxRow">
                  <input type="checkbox" {...onboardForm.register("dry_run")} />
                  Dry run only
                </label>
                <div className="toolbar">
                  <button className="button" type="submit" disabled={actionLoading}>
                    {actionLoading ? "Running…" : "Create Operator"}
                  </button>
                </div>
              </fieldset>
            </form>

            <form className="panel" onSubmit={handleOffboardSubmit} noValidate data-tour-target="offboard-form">
              <div className="panelHeader">
                <div>
                  <h3>Off-board Operator</h3>
                  <p>Disable one operator through the same governed backend used by the CLI path.</p>
                </div>
              </div>
              <fieldset className="formBody" disabled={actionLoading}>
                <FormStatus
                  isSubmitting={offboardForm.formState.isSubmitting}
                  isDirty={offboardForm.formState.isDirty}
                  submitCount={offboardForm.formState.submitCount}
                  errorCount={offboardErrorCount}
                  idleMessage="Schema validation keeps the off-boarding payload aligned with the backend."
                  helpHref={RUNBOOK_URLS.operatorOffboarding}
                  helpLabel="Open operator off-boarding runbook"
                />
                <div className="formGrid">
                  <FieldShell
                    htmlFor="offboard-operator"
                    label="Operator"
                    hint="Pick one operator from the live roster."
                    error={offboardForm.formState.errors.operator_id?.message}
                    touched={offboardForm.formState.touchedFields.operator_id}
                    required
                    stretch
                  >
                    <Controller
                      name="operator_id"
                      control={offboardForm.control}
                      render={({ field }) => (
                        <select
                          id="offboard-operator"
                          name={field.name}
                          ref={field.ref}
                          value={field.value}
                          onBlur={field.onBlur}
                          onChange={(event) => {
                            const nextId = event.target.value;
                            if (selectOperator(nextId)) {
                              field.onChange(nextId);
                              return;
                            }
                            field.onChange(selectedOperatorId);
                          }}
                          aria-invalid={Boolean(offboardForm.formState.errors.operator_id)}
                        >
                          <option value="">Select operator</option>
                          {operators.map((operator) => (
                            <option key={operator.id} value={operator.id}>
                              {operator.name} ({operator.role}, {operator.status})
                            </option>
                          ))}
                        </select>
                      )}
                    />
                  </FieldShell>

                  <FieldShell
                    htmlFor="offboard-reason"
                    label="Reason"
                    hint="Optional audit note for the off-boarding event."
                    error={offboardForm.formState.errors.reason?.message}
                    touched={offboardForm.formState.touchedFields.reason}
                    stretch
                  >
                    <textarea
                      id="offboard-reason"
                      {...offboardForm.register("reason")}
                      aria-invalid={Boolean(offboardForm.formState.errors.reason)}
                      placeholder="optional audit note"
                    />
                  </FieldShell>
                </div>
                <label className="checkboxRow">
                  <input type="checkbox" {...offboardForm.register("dry_run")} />
                  Dry run only
                </label>
                <div className="toolbar">
                  <button className="buttonDanger" type="submit" disabled={actionLoading || !offboardOperatorId}>
                    {actionLoading ? "Running…" : "Off-board Operator"}
                  </button>
                </div>
              </fieldset>
            </form>

            <form className="panel" onSubmit={handleSyncSubmit} noValidate>
              <div className="panelHeader">
                <div>
                  <h3>Reconcile Roster</h3>
                  <p>Force the live identity systems to match the merged operator roster.</p>
                </div>
              </div>
              <fieldset className="formBody" disabled={actionLoading}>
                <FormStatus
                  isSubmitting={syncForm.formState.isSubmitting}
                  isDirty={syncForm.formState.isDirty}
                  submitCount={syncForm.formState.submitCount}
                  errorCount={syncErrorCount}
                  idleMessage="Schema validation keeps reconciliation scope explicit before submit."
                  helpHref={RUNBOOK_URLS.operatorAdmin}
                  helpLabel="Open operator admin runbook"
                />
                <div className="formGrid">
                  <FieldShell
                    htmlFor="sync-operator"
                    label="Scope"
                    hint="Leave blank to reconcile the full operator roster."
                    error={syncForm.formState.errors.operator_id?.message}
                    touched={syncForm.formState.touchedFields.operator_id}
                    stretch
                  >
                    <select
                      id="sync-operator"
                      {...syncForm.register("operator_id")}
                      aria-invalid={Boolean(syncForm.formState.errors.operator_id)}
                    >
                      <option value="">All operators</option>
                      {operators.map((operator) => (
                        <option key={operator.id} value={operator.id}>
                          {operator.name}
                        </option>
                      ))}
                    </select>
                  </FieldShell>
                </div>
                <label className="checkboxRow">
                  <input type="checkbox" {...syncForm.register("dry_run")} />
                  Dry run only
                </label>
                <div className="toolbar">
                  <button className="buttonGhost" type="submit" disabled={actionLoading}>
                    {actionLoading ? "Running…" : "Reconcile"}
                  </button>
                </div>
              </fieldset>
            </form>
          </div>

          <section className="resultPanel" data-tour-target="action-result-panel">
            <div className="panelHeader">
              <div>
                <h3>Latest Result</h3>
                <p>{actionResult.title}</p>
              </div>
            </div>
            <StateGuidanceCard state={resultState} compact eyebrow="Latest Result State" />
            <pre>{actionResultPreview}</pre>
          </section>

          <section className="resultPanel" data-tour-target="inventory-panel">
            <div className="panelHeader">
              <div>
                <h3>Selected Operator Inventory</h3>
                <p>Live inventory check for the currently selected operator.</p>
              </div>
              <div className="toolbar">
                <button
                  className="buttonGhost"
                  onClick={() => selectedOperatorId && void inventoryQuery.refetch()}
                  disabled={!selectedOperatorId || inventoryQuery.isFetching}
                >
                  {inventoryQuery.isFetching ? "Loading…" : "Refresh Inventory"}
                </button>
              </div>
            </div>
            <div className="statusRow">
              <span className={`pill ${inventoryFeedback.toneClass}`}>{inventoryFeedback.label}</span>
              <span className="statusMeta">{inventoryFeedback.detail}</span>
            </div>
            {inventoryState.kind !== "success" ? <StateGuidanceCard state={inventoryState} compact eyebrow="Inventory State" /> : null}
            {selectedOperator ? (
              <div className="inventoryMeta">
                <span className="pill pillRole">{selectedOperator.name}</span>
                <span className={`pill ${pillToneClass(selectedOperator.status)}`}>{selectedOperator.status}</span>
                <span className="pill">{selectedOperator.role}</span>
                <span className="pill">{selectedOperator.keycloak_username || "no username"}</span>
              </div>
            ) : null}
            <pre>
              {inventoryQuery.data
                ? prettyJson(inventoryQuery.data)
                : inventoryQuery.error
                  ? prettyJson({ status: "error", message: getErrorMessage(inventoryQuery.error) })
                  : "Select an operator to inspect their access inventory."}
            </pre>
          </section>
        </aside>
      </div>
    </div>
  );
}

export default App;
