export type ChecklistItemId =
  | "identity_access"
  | "orientation"
  | "safe_first_task"
  | "search_success"
  | "help_recovery";

export type ChecklistItemDefinition = {
  id: ChecklistItemId;
  title: string;
  hint: string;
};

export type JourneyProgress = {
  visitorId: string;
  checklist: Record<ChecklistItemId, string | null>;
  firstSessionStartedAt: string | null;
};

export type JourneyEventInput = {
  eventType: string;
  stage?: string;
  milestone?: string;
  result?: string;
  flowId?: string | null;
  route?: string;
  checklistItem?: ChecklistItemId;
  durationMs?: number;
  properties?: Record<string, string | number | boolean | null | undefined>;
  plausible?: {
    pagePath?: string;
    eventName?: string;
  };
  glitchtip?: {
    requested: boolean;
    level?: string;
    message?: string;
  };
};

const SURFACE_ID = "windmill.operator_access_admin";
const PLAUSIBLE_SITE_DOMAIN = "ops.example.com";
const PLAUSIBLE_ENDPOINT = "https://analytics.example.com/api/event";
const JOURNEY_STORAGE_KEY = "lv3.operator_access_admin.journey.v1";
const JOURNEY_SESSION_KEY = "lv3.operator_access_admin.journey.session.v1";

const DEFAULT_CHECKLIST: Record<ChecklistItemId, string | null> = {
  identity_access: null,
  orientation: null,
  safe_first_task: null,
  search_success: null,
  help_recovery: null,
};

export const CHECKLIST_ITEMS: ChecklistItemDefinition[] = [
  {
    id: "identity_access",
    title: "Identity and access",
    hint: "The authenticated Windmill session reached the governed operator console.",
  },
  {
    id: "orientation",
    title: "Orientation",
    hint: "The first-run tour or equivalent orientation flow completed successfully.",
  },
  {
    id: "safe_first_task",
    title: "Safe first task",
    hint: "A read-only or reversible action, such as live inventory review, completed successfully.",
  },
  {
    id: "search_success",
    title: "Search success",
    hint: "Quick-filter search reached a useful destination without storing raw search terms.",
  },
  {
    id: "help_recovery",
    title: "Help and recovery",
    hint: "The help drawer led to a successful recovery or task completion path.",
  },
];

function canUseStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function nowIso(): string {
  return new Date().toISOString();
}

function randomId(prefix: string): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Math.random().toString(16).slice(2)}-${Date.now().toString(16)}`;
}

function readStoredProgress(): JourneyProgress {
  if (!canUseStorage()) {
    return {
      visitorId: randomId("visitor"),
      checklist: { ...DEFAULT_CHECKLIST },
      firstSessionStartedAt: null,
    };
  }
  try {
    const raw = window.localStorage.getItem(JOURNEY_STORAGE_KEY);
    if (!raw) {
      return {
        visitorId: randomId("visitor"),
        checklist: { ...DEFAULT_CHECKLIST },
        firstSessionStartedAt: null,
      };
    }
    const parsed = JSON.parse(raw) as Partial<JourneyProgress>;
    return {
      visitorId: typeof parsed.visitorId === "string" && parsed.visitorId ? parsed.visitorId : randomId("visitor"),
      checklist: {
        ...DEFAULT_CHECKLIST,
        ...(parsed.checklist ?? {}),
      },
      firstSessionStartedAt:
        typeof parsed.firstSessionStartedAt === "string" && parsed.firstSessionStartedAt
          ? parsed.firstSessionStartedAt
          : null,
    };
  } catch {
    return {
      visitorId: randomId("visitor"),
      checklist: { ...DEFAULT_CHECKLIST },
      firstSessionStartedAt: null,
    };
  }
}

function persistProgress(progress: JourneyProgress): JourneyProgress {
  if (!canUseStorage()) {
    return progress;
  }
  try {
    window.localStorage.setItem(JOURNEY_STORAGE_KEY, JSON.stringify(progress));
  } catch {
    // Ignore storage failures so analytics does not block the UI.
  }
  return progress;
}

function ensureSessionId(): string {
  if (typeof window === "undefined" || typeof window.sessionStorage === "undefined") {
    return randomId("session");
  }
  try {
    const existing = window.sessionStorage.getItem(JOURNEY_SESSION_KEY);
    if (existing) {
      return existing;
    }
    const created = randomId("session");
    window.sessionStorage.setItem(JOURNEY_SESSION_KEY, created);
    return created;
  } catch {
    return randomId("session");
  }
}

export function readJourneyProgress(): JourneyProgress {
  const progress = readStoredProgress();
  return persistProgress(progress);
}

export function createFlowId(): string {
  return randomId("flow");
}

export function canonicalJourneyUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `https://${PLAUSIBLE_SITE_DOMAIN}${normalizedPath}`;
}

function buildPlausibleProps(input: JourneyEventInput): Record<string, string> {
  const props: Record<string, string> = {
    surface: "operator_access_admin",
    event_type: input.eventType,
  };
  if (input.stage) {
    props.stage = input.stage;
  }
  if (input.milestone) {
    props.milestone = input.milestone;
  }
  if (input.result) {
    props.result = input.result;
  }
  if (input.checklistItem) {
    props.checklist_item = input.checklistItem;
  }
  const propertySource = input.properties ?? {};
  for (const [key, value] of Object.entries(propertySource)) {
    if (value === undefined || value === null) {
      continue;
    }
    props[key] = String(value);
    if (Object.keys(props).length >= 12) {
      break;
    }
  }
  return props;
}

function postPlausible(payload: Record<string, unknown>): void {
  if (typeof fetch !== "function") {
    return;
  }
  void fetch(PLAUSIBLE_ENDPOINT, {
    method: "POST",
    mode: "no-cors",
    keepalive: true,
    headers: {
      "Content-Type": "text/plain",
    },
    body: JSON.stringify(payload),
  }).catch(() => {
    // Ignore delivery failures; the durable backend ledger remains authoritative.
  });
}

function emitPlausibleEvents(input: JourneyEventInput): void {
  if (!input.plausible?.pagePath && !input.plausible?.eventName) {
    return;
  }
  const pagePath = input.plausible.pagePath ?? "/journeys/operator-access-admin/checklist";
  const url = canonicalJourneyUrl(pagePath);
  postPlausible({
    name: "pageview",
    url,
    domain: PLAUSIBLE_SITE_DOMAIN,
    props: buildPlausibleProps(input),
  });
  if (input.plausible.eventName) {
    postPlausible({
      name: input.plausible.eventName,
      url,
      domain: PLAUSIBLE_SITE_DOMAIN,
      props: buildPlausibleProps(input),
    });
  }
}

export function emitJourneyEvent(backend: Record<string, (args?: any) => Promise<any>>, input: JourneyEventInput): JourneyProgress {
  const progress = readJourneyProgress();
  const payload = {
    surface: SURFACE_ID,
    visitor_id: progress.visitorId,
    session_id: ensureSessionId(),
    occurred_at: nowIso(),
    event_type: input.eventType,
    stage: input.stage,
    milestone: input.milestone,
    result: input.result,
    flow_id: input.flowId ?? undefined,
    route: input.route,
    checklist_item: input.checklistItem,
    duration_ms: input.durationMs,
    properties: input.properties,
    plausible: input.plausible
      ? {
          site_domain: PLAUSIBLE_SITE_DOMAIN,
          page_path: input.plausible.pagePath,
          event_name: input.plausible.eventName,
          attempted: true,
        }
      : undefined,
    glitchtip: input.glitchtip ?? { requested: false },
  };
  emitPlausibleEvents(input);
  if (backend.record_journey_event) {
    void backend.record_journey_event({ event_json: JSON.stringify(payload) });
  }
  return progress;
}

export function completeChecklistItem(
  backend: Record<string, (args?: any) => Promise<any>>,
  itemId: ChecklistItemId,
  input: Omit<JourneyEventInput, "eventType" | "checklistItem">,
): JourneyProgress {
  const progress = readJourneyProgress();
  if (progress.checklist[itemId]) {
    return progress;
  }
  const occurredAt = nowIso();
  const nextProgress: JourneyProgress = {
    ...progress,
    checklist: {
      ...progress.checklist,
      [itemId]: occurredAt,
    },
    firstSessionStartedAt:
      itemId === "identity_access" && !progress.firstSessionStartedAt ? occurredAt : progress.firstSessionStartedAt,
  };
  persistProgress(nextProgress);
  emitJourneyEvent(backend, {
    ...input,
    eventType: "checklist_item_completed",
    checklistItem: itemId,
    result: input.result ?? "success",
    plausible: input.plausible ?? {
      pagePath: "/journeys/operator-access-admin/checklist",
      eventName: "Checklist Item Completed",
    },
  });
  return nextProgress;
}

export function recordInitialSessionStart(backend: Record<string, (args?: any) => Promise<any>>): JourneyProgress {
  const progress = readJourneyProgress();
  if (!progress.firstSessionStartedAt) {
    const occurredAt = nowIso();
    persistProgress({
      ...progress,
      firstSessionStartedAt: occurredAt,
    });
  }
  emitJourneyEvent(backend, {
    eventType: "session_started",
    stage: "identity_access",
    milestone: "authenticated_session_ready",
    result: "success",
    route: "/operator-access-admin",
    plausible: {
      pagePath: "/journeys/operator-access-admin/start",
      eventName: "Journey Session Started",
    },
  });
  return completeChecklistItem(backend, "identity_access", {
    stage: "identity_access",
    milestone: "authenticated_session_ready",
    route: "/operator-access-admin",
  });
}
