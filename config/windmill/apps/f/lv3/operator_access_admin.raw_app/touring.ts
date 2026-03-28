import Shepherd from "shepherd.js";
import type { StepOptions, StepOptionsButton, Tour } from "shepherd.js";
import "shepherd.js/dist/css/shepherd.css";

export type OnboardingRole = "admin" | "operator" | "viewer";

export type TourIntent =
  | "first_run"
  | "onboard_privileged"
  | "onboard_viewer"
  | "offboard"
  | "inventory";

export type TourOutcome = "idle" | "running" | "completed" | "dismissed";

export type TourProgress = {
  autoPrompted: boolean;
  lastIntent: TourIntent | null;
  lastStepId: string | null;
  lastOutcome: TourOutcome;
  lastCompletedAt: string | null;
  lastDismissedAt: string | null;
  updatedAt: string | null;
};

export type TourRuntimeContext = {
  intendedRole: OnboardingRole;
  selectedOperatorName: string | null;
  selectedOperatorStatus: string | null;
  hasOperators: boolean;
};

type StartTourOptions = {
  intent: TourIntent;
  context: TourRuntimeContext;
  autoPrompted?: boolean;
  resumeFromStepId?: string | null;
  onProgress: (progress: TourProgress) => void;
  onRunningChange: (running: boolean) => void;
};

const TOUR_STORAGE_KEY = "lv3.operator_access_admin.shepherd.v1";

const DEFAULT_PROGRESS: TourProgress = {
  autoPrompted: false,
  lastIntent: null,
  lastStepId: null,
  lastOutcome: "idle",
  lastCompletedAt: null,
  lastDismissedAt: null,
  updatedAt: null,
};

const DOCS_BASE_URL = "https://docs.lv3.org";
const ADMIN_RUNBOOK_URL = `${DOCS_BASE_URL}/runbooks/windmill-operator-access-admin/`;
const ONBOARD_RUNBOOK_URL = `${DOCS_BASE_URL}/runbooks/operator-onboarding/`;
const OFFBOARD_RUNBOOK_URL = `${DOCS_BASE_URL}/runbooks/operator-offboarding/`;

function canUseStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function nowIso(): string {
  return new Date().toISOString();
}

function persistTourProgress(progress: TourProgress): TourProgress {
  if (!canUseStorage()) {
    return progress;
  }
  try {
    window.localStorage.setItem(TOUR_STORAGE_KEY, JSON.stringify(progress));
  } catch {
    // Ignore storage failures so the tour still works in restrictive browsers.
  }
  return progress;
}

export function readTourProgress(): TourProgress {
  if (!canUseStorage()) {
    return DEFAULT_PROGRESS;
  }
  try {
    const raw = window.localStorage.getItem(TOUR_STORAGE_KEY);
    if (!raw) {
      return DEFAULT_PROGRESS;
    }
    return {
      ...DEFAULT_PROGRESS,
      ...(JSON.parse(raw) as Partial<TourProgress>),
    };
  } catch {
    return DEFAULT_PROGRESS;
  }
}

export function writeTourProgress(next: Partial<TourProgress>): TourProgress {
  return persistTourProgress({
    ...readTourProgress(),
    ...next,
    updatedAt: nowIso(),
  });
}

function docLink(label: string, href: string): string {
  return `<a href="${href}" target="_blank" rel="noreferrer">${label}</a>`;
}

function privilegedRoleLabel(role: OnboardingRole): string {
  if (role === "admin") {
    return "admin";
  }
  if (role === "viewer") {
    return "operator";
  }
  return role;
}

function selectedOperatorLabel(context: TourRuntimeContext): string {
  if (!context.selectedOperatorName) {
    return context.hasOperators ? "the selected operator" : "the next operator you create";
  }
  if (!context.selectedOperatorStatus) {
    return context.selectedOperatorName;
  }
  return `${context.selectedOperatorName} (${context.selectedOperatorStatus})`;
}

function backButton(): StepOptionsButton {
  return {
    text: "Back",
    secondary: true,
    action() {
      this.back();
    },
  };
}

function nextButton(text = "Next"): StepOptionsButton {
  return {
    text,
    action() {
      this.next();
    },
  };
}

function finishButton(): StepOptionsButton {
  return {
    text: "Finish",
    action() {
      this.complete();
    },
  };
}

function skipButton(): StepOptionsButton {
  return {
    text: "Skip Tour",
    secondary: true,
    action() {
      void this.cancel();
    },
  };
}

function firstRunSteps(context: TourRuntimeContext): StepOptions[] {
  return [
    {
      id: "first-run-launcher",
      attachTo: { element: '[data-tour-target="tour-launcher"]', on: "bottom-start" },
      title: "Choose the help path that matches your task",
      text: `
        <p>This browser-first admin surface now ships with Shepherd tours for first-run operators and repeat tasks.</p>
        <p>Every walkthrough is task-oriented, safe to skip, and points back to ${docLink("the admin runbook", ADMIN_RUNBOOK_URL)} when you need the full procedure.</p>
      `,
      buttons: [skipButton(), nextButton()],
    },
    {
      id: "first-run-roster",
      attachTo: { element: '[data-tour-target="roster-panel"]', on: "right-start" },
      title: "Start by reading the governed roster",
      text: `
        <p>The roster reflects the repo-authoritative operator list and is the fastest way to understand who already has access.</p>
        <p>Use it with ${docLink("the onboarding runbook", ONBOARD_RUNBOOK_URL)} before you add or disable identities.</p>
      `,
      buttons: [backButton(), skipButton(), nextButton()],
    },
    {
      id: "first-run-onboard",
      attachTo: { element: '[data-tour-target="onboard-form"]', on: "left-start" },
      title: "Create access through the governed workflow",
      text: `
        <p>This form calls the same ADR 0108 backend used by the CLI. It does not create a second provisioning path.</p>
        <p>For role rules, SSH key expectations, and optional integrations, open ${docLink("Operator Onboarding", ONBOARD_RUNBOOK_URL)}.</p>
      `,
      buttons: [backButton(), skipButton(), nextButton()],
    },
    {
      id: "first-run-offboard",
      attachTo: { element: '[data-tour-target="offboard-form"]', on: "left-start" },
      title: "Off-board without deleting the audit trail",
      text: `
        <p>Off-boarding disables access in the live identity systems while preserving the governed operator record and inventory history.</p>
        <p>Use ${docLink("the off-boarding runbook", OFFBOARD_RUNBOOK_URL)} when the change is urgent, audited, or partially failed.</p>
      `,
      buttons: [backButton(), skipButton(), nextButton()],
    },
    {
      id: "first-run-inventory",
      attachTo: { element: '[data-tour-target="inventory-panel"]', on: "left-start" },
      title: "Verify the live state before you trust it",
      text: `
        <p>The selected operator inventory shows what the live systems currently believe for ${selectedOperatorLabel(context)}.</p>
        <p>That makes it the quickest final check after onboarding, reconciliation, or off-boarding. Keep ${docLink("the admin runbook", ADMIN_RUNBOOK_URL)} nearby if something looks inconsistent.</p>
      `,
      buttons: [backButton(), finishButton()],
    },
  ];
}

function privilegedOnboardingSteps(context: TourRuntimeContext): StepOptions[] {
  const roleLabel = privilegedRoleLabel(context.intendedRole);
  return [
    {
      id: "onboard-privileged-launcher",
      attachTo: { element: '[data-tour-target="tour-launcher"]', on: "bottom-start" },
      title: `Walk through ${roleLabel} onboarding`,
      text: `
        <p>This walkthrough focuses on creating a privileged human operator with the same governed backend used by the CLI.</p>
        <p>Keep ${docLink("Operator Onboarding", ONBOARD_RUNBOOK_URL)} open for the full policy and post-login checklist.</p>
      `,
      buttons: [skipButton(), nextButton()],
    },
    {
      id: "onboard-privileged-role",
      attachTo: { element: '[data-tour-target="role-field"]', on: "left" },
      title: "Confirm the target role before you submit",
      text: `
        <p>Use <strong>${roleLabel}</strong> only when the new operator needs interactive access beyond read-only review.</p>
        <p>This decision controls the realm role mapping, group assignment, and the SSH expectations documented in ${docLink("the onboarding runbook", ONBOARD_RUNBOOK_URL)}.</p>
      `,
      buttons: [backButton(), skipButton(), nextButton()],
    },
    {
      id: "onboard-privileged-ssh",
      attachTo: { element: '[data-tour-target="ssh-key-field"]', on: "left" },
      title: "Privileged roles still require an SSH public key",
      text: `
        <p>${roleLabel === "admin" ? "Admins" : "Operators"} are expected to manage hosts and guests through the governed SSH path, so the public key remains required here.</p>
        <p>If you do not need SSH access, switch to the viewer flow instead and follow ${docLink("the same runbook section", ONBOARD_RUNBOOK_URL)} for the narrower role contract.</p>
      `,
      buttons: [backButton(), skipButton(), nextButton()],
    },
    {
      id: "onboard-privileged-result",
      attachTo: { element: '[data-tour-target="action-result-panel"]', on: "left-start" },
      title: "Capture the one-time result and verify inventory",
      text: `
        <p>The latest result panel is where the bootstrap password appears exactly once after a successful live create.</p>
        <p>Store it securely, direct the operator to rotate it immediately, then confirm the final state in the inventory panel and ${docLink("the admin runbook", ADMIN_RUNBOOK_URL)}.</p>
      `,
      buttons: [backButton(), finishButton()],
    },
  ];
}

function viewerOnboardingSteps(): StepOptions[] {
  return [
    {
      id: "onboard-viewer-launcher",
      attachTo: { element: '[data-tour-target="tour-launcher"]', on: "bottom-start" },
      title: "Use the viewer flow for read-only humans",
      text: `
        <p>This walkthrough is for operators who need read-only access without the SSH path that admins and operators receive.</p>
        <p>Use ${docLink("Operator Onboarding", ONBOARD_RUNBOOK_URL)} if you need the full approval and post-login checklist.</p>
      `,
      buttons: [skipButton(), nextButton()],
    },
    {
      id: "onboard-viewer-role",
      attachTo: { element: '[data-tour-target="role-field"]', on: "left" },
      title: "Set the role to viewer before you continue",
      text: `
        <p>The viewer role keeps the identity path narrow and avoids granting interactive host access.</p>
        <p>That makes it the right choice for reviewers, auditors, and humans who only need visibility across the platform surfaces.</p>
      `,
      buttons: [backButton(), skipButton(), nextButton()],
    },
    {
      id: "onboard-viewer-ssh",
      attachTo: { element: '[data-tour-target="ssh-key-field"]', on: "left" },
      title: "Viewer onboarding does not require an SSH key",
      text: `
        <p>This field stays optional for viewers because the role does not include SSH access.</p>
        <p>If your access plan changes, restart the privileged onboarding tour or follow ${docLink("the onboarding runbook", ONBOARD_RUNBOOK_URL)} to re-evaluate the role choice.</p>
      `,
      buttons: [backButton(), skipButton(), nextButton()],
    },
    {
      id: "onboard-viewer-result",
      attachTo: { element: '[data-tour-target="action-result-panel"]', on: "left-start" },
      title: "Finish with the same result and inventory checks",
      text: `
        <p>The result panel still returns the one-time bootstrap secret after a successful live create.</p>
        <p>Use the inventory panel afterward to confirm the viewer landed in the expected read-only state described in ${docLink("the admin runbook", ADMIN_RUNBOOK_URL)}.</p>
      `,
      buttons: [backButton(), finishButton()],
    },
  ];
}

function offboardingSteps(context: TourRuntimeContext): StepOptions[] {
  return [
    {
      id: "offboard-launcher",
      attachTo: { element: '[data-tour-target="tour-launcher"]', on: "bottom-start" },
      title: "Use the guided off-boarding path when you need speed with auditability",
      text: `
        <p>This walkthrough keeps the operator record, disables the live identities, and points back to the authoritative procedure when a step partially fails.</p>
        <p>Open ${docLink("Operator Offboarding", OFFBOARD_RUNBOOK_URL)} for the full recovery and rerun guidance.</p>
      `,
      buttons: [skipButton(), nextButton()],
    },
    {
      id: "offboard-roster",
      attachTo: { element: '[data-tour-target="roster-panel"]', on: "right-start" },
      title: "Select the person you intend to disable",
      text: `
        <p>The roster is where you confirm the current operator identity before you disable access for ${selectedOperatorLabel(context)}.</p>
        <p>${context.hasOperators ? "Clicking a row keeps the form and inventory view aligned on the same person." : "If the roster is empty, there is nothing live to off-board yet."}</p>
      `,
      buttons: [backButton(), skipButton(), nextButton()],
    },
    {
      id: "offboard-form",
      attachTo: { element: '[data-tour-target="offboard-form"]', on: "left-start" },
      title: "Record the reason and use dry-run when you need a preview",
      text: `
        <p>The off-boarding form writes the audit note, disables the live identities, and supports a dry run when you want to preview the plan first.</p>
        <p>That matches the failure-handling advice in ${docLink("the off-boarding runbook", OFFBOARD_RUNBOOK_URL)}.</p>
      `,
      buttons: [backButton(), skipButton(), nextButton()],
    },
    {
      id: "offboard-result",
      attachTo: { element: '[data-tour-target="action-result-panel"]', on: "left-start" },
      title: "Read the structured result before you leave the page",
      text: `
        <p>Use the latest result to confirm which systems succeeded, which ones were skipped, and whether a rerun is required.</p>
        <p>Then refresh the live inventory to make sure the disabled state matches ${docLink("the runbook", OFFBOARD_RUNBOOK_URL)}.</p>
      `,
      buttons: [backButton(), finishButton()],
    },
  ];
}

function inventorySteps(context: TourRuntimeContext): StepOptions[] {
  return [
    {
      id: "inventory-launcher",
      attachTo: { element: '[data-tour-target="tour-launcher"]', on: "bottom-start" },
      title: "Use inventory review as the final confidence check",
      text: `
        <p>This walkthrough is for validating the current live state after onboarding, reconciliation, or off-boarding.</p>
        <p>It complements ${docLink("the admin runbook", ADMIN_RUNBOOK_URL)} rather than replacing it.</p>
      `,
      buttons: [skipButton(), nextButton()],
    },
    {
      id: "inventory-roster",
      attachTo: { element: '[data-tour-target="roster-panel"]', on: "right-start" },
      title: "Pick the person you want to verify",
      text: `
        <p>Select a roster entry before you read the live inventory for ${selectedOperatorLabel(context)}.</p>
        <p>${context.hasOperators ? "The selected row drives both the off-boarding form and the inventory view." : "No roster entries exist yet, so the inventory panel will stay empty."}</p>
      `,
      buttons: [backButton(), skipButton(), nextButton()],
    },
    {
      id: "inventory-panel",
      attachTo: { element: '[data-tour-target="inventory-panel"]', on: "left-start" },
      title: "Read the live inventory from the platform, not from memory",
      text: `
        <p>This panel queries the live systems for the currently selected operator and is the fastest way to confirm drift, missing entities, or a completed repair.</p>
        <p>Refresh it after any mutation and compare the result with ${docLink("the onboarding runbook", ONBOARD_RUNBOOK_URL)} or ${docLink("the off-boarding runbook", OFFBOARD_RUNBOOK_URL)}.</p>
      `,
      buttons: [backButton(), finishButton()],
    },
  ];
}

function buildSteps(intent: TourIntent, context: TourRuntimeContext): StepOptions[] {
  switch (intent) {
    case "onboard_privileged":
      return privilegedOnboardingSteps(context);
    case "onboard_viewer":
      return viewerOnboardingSteps();
    case "offboard":
      return offboardingSteps(context);
    case "inventory":
      return inventorySteps(context);
    case "first_run":
    default:
      return firstRunSteps(context);
  }
}

export function tourIntentLabel(intent: TourIntent | null | undefined): string {
  switch (intent) {
    case "first_run":
      return "First-run tour";
    case "onboard_privileged":
      return "Admin/operator onboarding";
    case "onboard_viewer":
      return "Viewer onboarding";
    case "offboard":
      return "Off-boarding";
    case "inventory":
      return "Inventory review";
    default:
      return "Guided tour";
  }
}

export function startOperatorAccessTour({
  intent,
  context,
  autoPrompted = false,
  resumeFromStepId,
  onProgress,
  onRunningChange,
}: StartTourOptions): Tour {
  const tour = new Shepherd.Tour({
    tourName: `operator-access-admin-${intent}`,
    confirmCancel: true,
    confirmCancelMessage: "Close this guided tour? You can resume it later from the Guided onboarding launcher.",
    keyboardNavigation: true,
    exitOnEsc: true,
    useModalOverlay: true,
    defaultStepOptions: {
      cancelIcon: {
        enabled: true,
        label: "Close guided onboarding",
      },
      classes: "lv3TourTooltip",
      highlightClass: "lv3TourTarget",
      scrollTo: {
        behavior: "smooth",
        block: "center",
      },
      canClickTarget: false,
      modalOverlayOpeningPadding: 10,
      modalOverlayOpeningRadius: 20,
    },
  });

  tour.addSteps(buildSteps(intent, context));

  tour.on("start", () => {
    onRunningChange(true);
    onProgress(
      writeTourProgress({
        autoPrompted,
        lastIntent: intent,
        lastOutcome: "running",
      }),
    );
  });

  tour.on("show", (event: { step?: { id?: string } }) => {
    onProgress(
      writeTourProgress({
        autoPrompted,
        lastIntent: intent,
        lastStepId: event.step?.id ?? null,
        lastOutcome: "running",
      }),
    );
  });

  tour.on("complete", () => {
    onRunningChange(false);
    onProgress(
      writeTourProgress({
        autoPrompted,
        lastIntent: intent,
        lastStepId: null,
        lastOutcome: "completed",
        lastCompletedAt: nowIso(),
      }),
    );
  });

  tour.on("cancel", () => {
    onRunningChange(false);
    onProgress(
      writeTourProgress({
        autoPrompted,
        lastIntent: intent,
        lastOutcome: "dismissed",
        lastDismissedAt: nowIso(),
      }),
    );
  });

  tour.start();

  if (resumeFromStepId && tour.getById(resumeFromStepId)) {
    tour.show(resumeFromStepId);
  }

  return tour;
}
