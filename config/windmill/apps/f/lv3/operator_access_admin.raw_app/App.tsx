import React, { ReactNode, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
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
};

type ToolbarButtonProps = {
  label: string;
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
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

function FormStatus({ isSubmitting, isDirty, submitCount, errorCount, idleMessage }: FormStatusProps) {
  let className = "banner bannerInfo bannerInline";
  let message = idleMessage;

  if (isSubmitting) {
    className = "banner bannerInfo bannerInline";
    message = "Validating and submitting through the governed backend.";
  } else if (submitCount > 0 && errorCount > 0) {
    className = "banner bannerError bannerInline";
    message =
      errorCount === 1
        ? "Resolve the highlighted field before submitting."
        : `Resolve ${errorCount} highlighted fields before submitting.`;
  } else if (isDirty) {
    className = "banner bannerInfo bannerInline";
    message = "Schema validation is active for this form. Touched fields update inline.";
  }

  return <div className={className}>{message}</div>;
}

function App() {
  const [roster, setRoster] = useState<RosterPayload | null>(null);
  const [rosterLoading, setRosterLoading] = useState(true);
  const [rosterError, setRosterError] = useState("");
  const [selectedOperatorId, setSelectedOperatorId] = useState("");
  const [quickFilterText, setQuickFilterText] = useState("");
  const [displayedOperatorCount, setDisplayedOperatorCount] = useState(0);
  const [mentionTarget, setMentionTarget] = useState("");
  const [notesMarkdown, setNotesMarkdown] = useState("");
  const [actionLoading, setActionLoading] = useState(false);
  const [actionTitle, setActionTitle] = useState("No action executed yet");
  const [actionPayload, setActionPayload] = useState<ActionPayload | null>(null);
  const [inventoryPayload, setInventoryPayload] = useState<InventoryPayload | null>(null);
  const [inventoryLoading, setInventoryLoading] = useState(false);
  const gridApiRef = useRef<GridApi<OperatorRecord> | null>(null);
  const deferredQuickFilterText = useDeferredValue(quickFilterText);
  const [tourProgress, setTourProgress] = useState<TourProgress>(() => readTourProgress());
  const [tourRunning, setTourRunning] = useState(false);
  const tourRef = useRef<Tour | null>(null);
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

  const operators = roster?.operators ?? [];
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

  async function refreshRoster(): Promise<string> {
    setRosterLoading(true);
    setRosterError("");
    try {
      const payload = await backend.list_operators({});
      if (!isRosterPayload(payload)) {
        setRoster(null);
        setSelectedOperatorId("");
        setInventoryPayload(null);
        offboardForm.reset(offboardFormDefaults);
        setRosterError(extractRosterError((payload ?? {}) as RosterPayloadError));
        return "";
      }

      setRoster(payload);

      const nextSelectedOperatorId = payload.operators.length
        ? payload.operators.some((item) => item.id === selectedOperatorId)
          ? selectedOperatorId
          : payload.operators[0].id
        : "";

      setSelectedOperatorId(nextSelectedOperatorId);
      offboardForm.setValue("operator_id", nextSelectedOperatorId, {
        shouldValidate: offboardForm.formState.submitCount > 0,
      });

      if (!nextSelectedOperatorId) {
        setInventoryPayload(null);
      }

      return nextSelectedOperatorId;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setRosterError(message);
      return "";
    } finally {
      setRosterLoading(false);
    }
  }

  async function loadInventory(operatorId: string) {
    if (!operatorId) {
      setInventoryPayload(null);
      return;
    }
    setInventoryLoading(true);
    try {
      const payload = (await backend.operator_inventory({
        operator_id: operatorId,
        offline: false,
        dry_run: false,
      })) as InventoryPayload;
      setInventoryPayload(payload);
    } finally {
      setInventoryLoading(false);
    }
  }

  useEffect(() => {
    void refreshRoster();
  }, []);

  useEffect(() => {
    offboardForm.setValue("operator_id", selectedOperatorId, {
      shouldValidate: offboardForm.formState.submitCount > 0,
    });
  }, [selectedOperatorId, offboardForm]);

  useEffect(() => {
    if (!selectedOperatorId) {
      setInventoryPayload(null);
      return;
    }
    void loadInventory(selectedOperatorId);
  }, [selectedOperatorId]);

  useEffect(() => {
    setNotesMarkdown(selectedOperatorNotes);
    setMentionTarget(selectedOperator?.id ?? "");
  }, [selectedOperator?.id, selectedOperatorNotes]);

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
    return () => {
      if (!tourRef.current) {
        return;
      }
      tourRef.current.hide();
      tourRef.current.steps.forEach((step) => step.destroy());
      tourRef.current = null;
    };
  }, []);

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
      onProgress: setTourProgress,
      onRunningChange: setTourRunning,
    });
  }

  useEffect(() => {
    if (!rosterLoading && !rosterError && !tourProgress.autoPrompted && !tourRunning) {
      launchTour("first_run", { autoPrompted: true });
    }
  }, [rosterLoading, rosterError, tourProgress.autoPrompted, tourRunning]);

  async function executeAction(title: string, runner: () => Promise<ActionPayload>, refresh = true) {
    setActionLoading(true);
    setActionTitle(title);
    try {
      const payload = await runner();
      setActionPayload(payload);
      if (refresh) {
        const nextSelectedOperatorId = await refreshRoster();
        if (nextSelectedOperatorId) {
          await loadInventory(nextSelectedOperatorId);
        }
      }
    } finally {
      setActionLoading(false);
    }
  }

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

  const handleOnboardSubmit = onboardForm.handleSubmit(async (values) => {
    await executeAction("Operator onboarding result", async () => {
      const payload = (await backend.create_operator(values)) as ActionPayload;
      if (payload.status === "ok" && !values.dry_run) {
        onboardForm.reset({
          ...onboardFormDefaults,
          role: values.role,
        });
      }
      return payload;
    });
  });

  const handleOffboardSubmit = offboardForm.handleSubmit(async (values) => {
    await executeAction("Operator off-boarding result", async () => backend.offboard_operator(values) as Promise<ActionPayload>);
  });

  const handleSyncSubmit = syncForm.handleSubmit(async (values) => {
    await executeAction("Operator roster reconciliation result", async () => backend.sync_operators(values) as Promise<ActionPayload>);
  });

  async function handleSaveNotes() {
    if (!selectedOperatorId) {
      return;
    }
    await executeAction(
      "Operator notes update result",
      async () =>
        (backend.update_operator_notes({
          operator_id: selectedOperatorId,
          notes_markdown: notesMarkdown,
          dry_run: false,
        }) as Promise<ActionPayload>),
    );
  }
  const onboardErrorCount = Object.keys(onboardForm.formState.errors).length;
  const offboardErrorCount = Object.keys(offboardForm.formState.errors).length;
  const syncErrorCount = Object.keys(syncForm.formState.errors).length;

  return (
    <div className="shell">
      <section className="hero">
        <div className="heroCard">
          <h1>Operator Access Admin</h1>
          <p>
            Browser-first access control for ADR 0108. This console combines schema-first forms,
            the data-dense AG Grid roster, task-specific guided tours, and bounded rich notes while
            keeping every mutation on the same repo-managed backend path.
          </p>
        </div>
        <div className="heroStats">
          <div className="heroCard stat">
            <span className="statLabel">Total Operators</span>
            <span className="statValue">{roster?.operator_count ?? "…"}</span>
          </div>
          <div className="heroCard stat">
            <span className="statLabel">Active</span>
            <span className="statValue">{roster?.active_count ?? "…"}</span>
          </div>
          <div className="heroCard stat">
            <span className="statLabel">Inactive</span>
            <span className="statValue">{roster?.inactive_count ?? "…"}</span>
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
        </div>
        <p className="tourFootnote">
          Need the full operating procedure?{" "}
          <a className="inlineLink" href="https://docs.lv3.org/runbooks/windmill-operator-access-admin/" target="_blank" rel="noreferrer">
            Open the operator admin runbook
          </a>
          .
        </p>
      </section>

      <div className="layout">
        <div className="mainColumn">
          <section className="panel" data-tour-target="roster-panel">
            <div className="panelHeader">
              <div>
                <h2>Roster</h2>
                <p>Current human operators from the repo-authoritative `config/operators.yaml` roster.</p>
              </div>
              <div className="toolbar">
                <button className="buttonGhost" onClick={() => void refreshRoster()} disabled={rosterLoading || actionLoading}>
                  {rosterLoading ? "Refreshing…" : "Refresh"}
                </button>
              </div>
            </div>

            {rosterError ? <div className="banner bannerError">{rosterError}</div> : null}
            {!rosterError ? (
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
                    rosterLoading ? '<span class="ag-overlay-loading-center">Loading operator roster…</span>' : "No operators found in the roster."
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
                <button className="buttonGhost" type="button" onClick={() => setNotesMarkdown(selectedOperatorNotes)} disabled={!notesDirty || actionLoading}>
                  Reset
                </button>
                <button className="button" type="button" onClick={() => void handleSaveNotes()} disabled={!selectedOperatorId || !notesDirty || actionLoading}>
                  {actionLoading ? "Saving…" : "Save Notes"}
                </button>
              </div>
            </div>

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
            ) : (
              <div className="emptyState">
                <h3>Select an operator</h3>
                <p>Choose one roster entry to open the bounded rich-content editor for that operator.</p>
              </div>
            )}
          </section>
        </div>

        <aside className="sidebar">
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
                <p>{actionTitle}</p>
              </div>
            </div>
            <pre>{actionPayload ? prettyJson(actionPayload) : "Run an action to inspect the structured result here."}</pre>
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
                  onClick={() => selectedOperatorId && void loadInventory(selectedOperatorId)}
                  disabled={!selectedOperatorId || inventoryLoading}
                >
                  {inventoryLoading ? "Loading…" : "Refresh Inventory"}
                </button>
              </div>
            </div>
            {selectedOperator ? (
              <div className="inventoryMeta">
                <span className="pill pillRole">{selectedOperator.name}</span>
                <span className={`pill ${pillToneClass(selectedOperator.status)}`}>{selectedOperator.status}</span>
                <span className="pill">{selectedOperator.role}</span>
                <span className="pill">{selectedOperator.keycloak_username || "no username"}</span>
              </div>
            ) : null}
            <pre>{inventoryPayload ? prettyJson(inventoryPayload) : "Select an operator to inspect their access inventory."}</pre>
          </section>
        </aside>
      </div>
    </div>
  );
}

export default App;
