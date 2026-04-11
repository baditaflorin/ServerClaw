export type PaletteLane = "start" | "observe" | "change" | "learn" | "recover";

export type PaletteKind =
  | "application"
  | "page"
  | "operator"
  | "quick_action"
  | "runbook"
  | "adr"
  | "glossary";

export type PaletteEntrySeed = {
  id: string;
  label: string;
  description: string;
  lane: PaletteLane;
  kind: PaletteKind;
  href?: string;
  keywords?: string[];
  newTab?: boolean;
  canFavorite?: boolean;
};

export type PaletteStorageState = {
  favoriteIds: string[];
  recentIds: string[];
};

export type PaletteSearchResult = {
  id: string;
  title: string;
  description: string;
  href: string;
  lane: PaletteLane;
  kind: Extract<PaletteKind, "runbook" | "adr">;
  collection: string;
  keywords: string[];
  score: number;
  sourcePath: string;
};

export const DOCS_BASE_URL = "https://docs.example.com";
export const HOME_BASE_URL = "https://home.example.com";
export const OPS_PORTAL_BASE_URL = "https://ops.example.com";
export const WINDMILL_BASE_URL = "http://100.64.0.1:8005";

export const paletteLaneLabels: Record<PaletteLane, string> = {
  start: "Start",
  observe: "Observe",
  change: "Change",
  learn: "Learn",
  recover: "Recover",
};

export const paletteKindLabels: Record<PaletteKind, string> = {
  application: "Application",
  page: "Page",
  operator: "Operator",
  quick_action: "Quick Action",
  runbook: "Runbook",
  adr: "ADR",
  glossary: "Glossary",
};

export const paletteStorageKey = "lv3.command_palette.operator_access_admin.v1";
export const paletteFavoriteLimit = 8;
export const paletteRecentLimit = 8;
export const defaultPaletteFavorites = [
  "page:roster",
  "page:onboard",
  "page:inventory",
  "app:docs",
];

export const paletteStaticEntries: PaletteEntrySeed[] = [
  {
    id: "app:docs",
    label: "Developer Portal",
    description: "Open the authenticated docs portal for ADRs, runbooks, and platform references.",
    lane: "learn",
    kind: "application",
    href: DOCS_BASE_URL,
    keywords: ["docs", "portal", "reference", "runbooks", "adrs"],
    newTab: true,
    canFavorite: true,
  },
  {
    id: "app:ops-portal",
    label: "Ops Portal",
    description: "Open the shared launcher, runbook entrypoints, and live platform dashboard.",
    lane: "observe",
    kind: "application",
    href: OPS_PORTAL_BASE_URL,
    keywords: ["ops", "portal", "launcher", "dashboard"],
    newTab: true,
    canFavorite: true,
  },
  {
    id: "app:homepage",
    label: "Homepage",
    description: "Open the unified platform home surface for shared service discovery.",
    lane: "start",
    kind: "application",
    href: HOME_BASE_URL,
    keywords: ["home", "homepage", "services", "start"],
    newTab: true,
    canFavorite: true,
  },
  {
    id: "app:windmill",
    label: "Windmill Workspace",
    description: "Open the private Windmill workspace that hosts the browser-first operator workflows.",
    lane: "change",
    kind: "application",
    href: `${WINDMILL_BASE_URL}/workspace/lv3`,
    keywords: ["windmill", "workspace", "lv3", "automation"],
    newTab: true,
    canFavorite: true,
  },
  {
    id: "glossary:totp",
    label: "Glossary: TOTP",
    description: "Time-based one-time password enrollment required for routine operator sign-in.",
    lane: "learn",
    kind: "glossary",
    href: `${DOCS_BASE_URL}/runbooks/operator-onboarding/`,
    keywords: ["totp", "mfa", "2fa", "authentication"],
    newTab: true,
  },
  {
    id: "glossary:tailnet",
    label: "Glossary: Tailnet",
    description: "The private Tailscale network path used for routine operator access and jump routing.",
    lane: "learn",
    kind: "glossary",
    href: `${DOCS_BASE_URL}/runbooks/configure-tailscale-access/`,
    keywords: ["tailnet", "tailscale", "mesh", "private access"],
    newTab: true,
  },
  {
    id: "glossary:break-glass",
    label: "Glossary: Break-glass",
    description: "Emergency-only access or recovery path that stays outside routine operations.",
    lane: "recover",
    kind: "glossary",
    href: `${DOCS_BASE_URL}/runbooks/break-glass/`,
    keywords: ["break glass", "emergency", "recovery", "fallback"],
    newTab: true,
  },
  {
    id: "glossary:identity-taxonomy",
    label: "Glossary: Identity Taxonomy",
    description: "The platform contract that distinguishes human, service, agent, and break-glass principals.",
    lane: "learn",
    kind: "glossary",
    href: `${DOCS_BASE_URL}/runbooks/identity-taxonomy-and-managed-principals/`,
    keywords: ["identity", "principal", "operator", "service", "agent"],
    newTab: true,
  },
];

function normalizeStoredIds(value: unknown, limit: number): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const ids = value
    .filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    .map((item) => item.trim());
  return Array.from(new Set(ids)).slice(0, limit);
}

export function readPaletteStorageState(): PaletteStorageState {
  if (typeof window === "undefined") {
    return {
      favoriteIds: [...defaultPaletteFavorites],
      recentIds: [],
    };
  }

  try {
    const raw = window.localStorage.getItem(paletteStorageKey);
    if (!raw) {
      return {
        favoriteIds: [...defaultPaletteFavorites],
        recentIds: [],
      };
    }
    const payload = JSON.parse(raw) as Partial<PaletteStorageState>;
    const favoriteIds = normalizeStoredIds(payload.favoriteIds, paletteFavoriteLimit);
    const recentIds = normalizeStoredIds(payload.recentIds, paletteRecentLimit);
    return {
      favoriteIds: favoriteIds.length > 0 ? favoriteIds : [...defaultPaletteFavorites],
      recentIds,
    };
  } catch {
    return {
      favoriteIds: [...defaultPaletteFavorites],
      recentIds: [],
    };
  }
}

export function writePaletteStorageState(next: PaletteStorageState): PaletteStorageState {
  const normalized = {
    favoriteIds: normalizeStoredIds(next.favoriteIds, paletteFavoriteLimit),
    recentIds: normalizeStoredIds(next.recentIds, paletteRecentLimit),
  };

  if (typeof window !== "undefined") {
    window.localStorage.setItem(paletteStorageKey, JSON.stringify(normalized));
  }

  return normalized;
}

export function togglePaletteFavorite(
  state: PaletteStorageState,
  itemId: string,
): PaletteStorageState {
  const favorites = state.favoriteIds.includes(itemId)
    ? state.favoriteIds.filter((favoriteId) => favoriteId !== itemId)
    : [itemId, ...state.favoriteIds];
  return writePaletteStorageState({
    favoriteIds: favorites,
    recentIds: state.recentIds,
  });
}

export function recordPaletteRecent(
  state: PaletteStorageState,
  itemId: string,
): PaletteStorageState {
  return writePaletteStorageState({
    favoriteIds: state.favoriteIds,
    recentIds: [itemId, ...state.recentIds.filter((recentId) => recentId !== itemId)],
  });
}
