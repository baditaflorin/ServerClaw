import React, { FormEvent, useEffect, useMemo, useState } from "react";
import { backend } from "./wmill";
import "./index.css";

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

type OnboardFormState = {
  name: string;
  email: string;
  role: "admin" | "operator" | "viewer";
  ssh_key: string;
  operator_id: string;
  keycloak_username: string;
  tailscale_login_email: string;
  tailscale_device_name: string;
  dry_run: boolean;
};

type OffboardFormState = {
  operator_id: string;
  reason: string;
  dry_run: boolean;
};

type SyncFormState = {
  operator_id: string;
  dry_run: boolean;
};

const initialOnboardState: OnboardFormState = {
  name: "",
  email: "",
  role: "operator",
  ssh_key: "",
  operator_id: "",
  keycloak_username: "",
  tailscale_login_email: "",
  tailscale_device_name: "",
  dry_run: false,
};

const initialOffboardState: OffboardFormState = {
  operator_id: "",
  reason: "",
  dry_run: false,
};

const initialSyncState: SyncFormState = {
  operator_id: "",
  dry_run: false,
};

function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function formatDate(value?: string): string {
  if (!value) {
    return "n/a";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
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

function App() {
  const [roster, setRoster] = useState<RosterPayload | null>(null);
  const [rosterLoading, setRosterLoading] = useState(true);
  const [rosterError, setRosterError] = useState("");
  const [selectedOperatorId, setSelectedOperatorId] = useState("");
  const [onboard, setOnboard] = useState<OnboardFormState>(initialOnboardState);
  const [offboard, setOffboard] = useState<OffboardFormState>(initialOffboardState);
  const [syncForm, setSyncForm] = useState<SyncFormState>(initialSyncState);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionTitle, setActionTitle] = useState("No action executed yet");
  const [actionPayload, setActionPayload] = useState<ActionPayload | null>(null);
  const [inventoryPayload, setInventoryPayload] = useState<InventoryPayload | null>(null);
  const [inventoryLoading, setInventoryLoading] = useState(false);

  const operators = roster?.operators ?? [];
  const selectedOperator = useMemo(
    () => operators.find((item) => item.id === selectedOperatorId) ?? null,
    [operators, selectedOperatorId],
  );

  async function refreshRoster() {
    setRosterLoading(true);
    setRosterError("");
    try {
      const payload = await backend.list_operators({});
      if (!isRosterPayload(payload)) {
        setRoster(null);
        setSelectedOperatorId("");
        setOffboard(initialOffboardState);
        setRosterError(extractRosterError((payload ?? {}) as RosterPayloadError));
        return;
      }
      setRoster(payload);
      if (!selectedOperatorId && payload.operators.length > 0) {
        const first = payload.operators[0].id;
        setSelectedOperatorId(first);
        setOffboard((current) => ({ ...current, operator_id: first }));
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setRosterError(message);
    } finally {
      setRosterLoading(false);
    }
  }

  async function loadInventory(operatorId: string) {
    if (!operatorId) {
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
    if (selectedOperatorId) {
      void loadInventory(selectedOperatorId);
    }
  }, [selectedOperatorId]);

  async function executeAction(title: string, runner: () => Promise<ActionPayload>, refresh = true) {
    setActionLoading(true);
    setActionTitle(title);
    try {
      const payload = await runner();
      setActionPayload(payload);
      if (refresh) {
        await refreshRoster();
        if (selectedOperatorId) {
          await loadInventory(selectedOperatorId);
        }
      }
    } finally {
      setActionLoading(false);
    }
  }

  async function handleOnboardSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await executeAction("Operator onboarding result", async () => {
      const payload = (await backend.create_operator(onboard)) as ActionPayload;
      if (payload.status === "ok" && !onboard.dry_run) {
        setOnboard((current) => ({
          ...initialOnboardState,
          role: current.role,
        }));
      }
      return payload;
    });
  }

  async function handleOffboardSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await executeAction("Operator off-boarding result", async () => backend.offboard_operator(offboard) as Promise<ActionPayload>);
  }

  async function handleSyncSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await executeAction("Operator roster reconciliation result", async () => backend.sync_operators(syncForm) as Promise<ActionPayload>);
  }

  const sshRequired = onboard.role !== "viewer";

  return (
    <div className="shell">
      <section className="hero">
        <div className="heroCard">
          <h1>Operator Access Admin</h1>
          <p>
            Browser-first access control for ADR 0108. This console wraps the repo-managed onboarding,
            off-boarding, inventory, and roster reconciliation workflows instead of creating a second
            provisioning path.
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

      <div className="layout">
        <section className="panel">
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
            <table className="rosterTable">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Keycloak</th>
                  <th>SSH</th>
                  <th>Onboarded</th>
                </tr>
              </thead>
              <tbody>
                {operators.map((operator) => (
                  <tr
                    key={operator.id}
                    className={operator.id === selectedOperatorId ? "isSelected" : ""}
                    onClick={() => {
                      setSelectedOperatorId(operator.id);
                      setOffboard((current) => ({ ...current, operator_id: operator.id }));
                    }}
                  >
                    <td>
                      <strong>{operator.name}</strong>
                      <div className="muted">{operator.email}</div>
                    </td>
                    <td>
                      <span className="pill pillRole">{operator.role}</span>
                    </td>
                    <td>
                      <span className={`pill ${operator.status === "active" ? "pillActive" : "pillInactive"}`}>
                        {operator.status}
                      </span>
                    </td>
                    <td>
                      <div>{operator.keycloak_username}</div>
                      <div className="muted">{operator.realm_roles.join(", ") || "n/a"}</div>
                    </td>
                    <td>{operator.ssh_enabled ? "enabled" : "not required"}</td>
                    <td>{formatDate(operator.onboarded_at)}</td>
                  </tr>
                ))}
                {!operators.length && !rosterLoading ? (
                  <tr>
                    <td colSpan={6}>No operators found in the roster.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>

        <aside className="sidebar">
          <div className="forms">
            <form className="panel" onSubmit={handleOnboardSubmit}>
              <div className="panelHeader">
                <div>
                  <h3>Onboard Operator</h3>
                  <p>Create a new human operator through the governed ADR 0108 workflow.</p>
                </div>
              </div>
              <div className="formGrid">
                <div className="formField">
                  <label>Name</label>
                  <input value={onboard.name} onChange={(event) => setOnboard({ ...onboard, name: event.target.value })} required />
                </div>
                <div className="formField">
                  <label>Email</label>
                  <input
                    type="email"
                    value={onboard.email}
                    onChange={(event) => setOnboard({ ...onboard, email: event.target.value })}
                    required
                  />
                </div>
                <div className="formField">
                  <label>Role</label>
                  <select
                    value={onboard.role}
                    onChange={(event) => setOnboard({ ...onboard, role: event.target.value as OnboardFormState["role"] })}
                  >
                    <option value="admin">admin</option>
                    <option value="operator">operator</option>
                    <option value="viewer">viewer</option>
                  </select>
                </div>
                <div className="formField">
                  <label>Operator ID</label>
                  <input
                    value={onboard.operator_id}
                    onChange={(event) => setOnboard({ ...onboard, operator_id: event.target.value })}
                    placeholder="optional slug"
                  />
                </div>
                <div className="formField">
                  <label>Keycloak Username</label>
                  <input
                    value={onboard.keycloak_username}
                    onChange={(event) => setOnboard({ ...onboard, keycloak_username: event.target.value })}
                    placeholder="optional username override"
                  />
                </div>
                <div className="formField">
                  <label>Tailscale Login Email</label>
                  <input
                    value={onboard.tailscale_login_email}
                    onChange={(event) => setOnboard({ ...onboard, tailscale_login_email: event.target.value })}
                    placeholder="optional override"
                  />
                </div>
                <div className="formField formFieldWide">
                  <label>SSH Public Key {sshRequired ? "(required)" : "(optional for viewer)"}</label>
                  <textarea
                    value={onboard.ssh_key}
                    onChange={(event) => setOnboard({ ...onboard, ssh_key: event.target.value })}
                    required={sshRequired}
                    placeholder="ssh-ed25519 AAAA..."
                  />
                </div>
                <div className="formField formFieldWide">
                  <label>Tailscale Device Name</label>
                  <input
                    value={onboard.tailscale_device_name}
                    onChange={(event) => setOnboard({ ...onboard, tailscale_device_name: event.target.value })}
                    placeholder="optional device label"
                  />
                </div>
              </div>
              <label className="checkboxRow">
                <input
                  type="checkbox"
                  checked={onboard.dry_run}
                  onChange={(event) => setOnboard({ ...onboard, dry_run: event.target.checked })}
                />
                Dry run only
              </label>
              <div className="toolbar">
                <button className="button" type="submit" disabled={actionLoading}>
                  {actionLoading ? "Running…" : "Create Operator"}
                </button>
              </div>
            </form>

            <form className="panel" onSubmit={handleOffboardSubmit}>
              <div className="panelHeader">
                <div>
                  <h3>Off-board Operator</h3>
                  <p>Disable one operator through the same governed backend used by the CLI path.</p>
                </div>
              </div>
              <div className="formGrid">
                <div className="formField formFieldWide">
                  <label>Operator</label>
                  <select
                    value={offboard.operator_id}
                    onChange={(event) => {
                      const nextId = event.target.value;
                      setOffboard({ ...offboard, operator_id: nextId });
                      setSelectedOperatorId(nextId);
                    }}
                    required
                  >
                    <option value="">Select operator</option>
                    {operators.map((operator) => (
                      <option key={operator.id} value={operator.id}>
                        {operator.name} ({operator.role}, {operator.status})
                      </option>
                    ))}
                  </select>
                </div>
                <div className="formField formFieldWide">
                  <label>Reason</label>
                  <textarea
                    value={offboard.reason}
                    onChange={(event) => setOffboard({ ...offboard, reason: event.target.value })}
                    placeholder="optional audit note"
                  />
                </div>
              </div>
              <label className="checkboxRow">
                <input
                  type="checkbox"
                  checked={offboard.dry_run}
                  onChange={(event) => setOffboard({ ...offboard, dry_run: event.target.checked })}
                />
                Dry run only
              </label>
              <div className="toolbar">
                <button className="buttonDanger" type="submit" disabled={actionLoading || !offboard.operator_id}>
                  {actionLoading ? "Running…" : "Off-board Operator"}
                </button>
              </div>
            </form>

            <form className="panel" onSubmit={handleSyncSubmit}>
              <div className="panelHeader">
                <div>
                  <h3>Reconcile Roster</h3>
                  <p>Force the live identity systems to match the merged operator roster.</p>
                </div>
              </div>
              <div className="formGrid">
                <div className="formField formFieldWide">
                  <label>Scope</label>
                  <select
                    value={syncForm.operator_id}
                    onChange={(event) => setSyncForm({ ...syncForm, operator_id: event.target.value })}
                  >
                    <option value="">All operators</option>
                    {operators.map((operator) => (
                      <option key={operator.id} value={operator.id}>
                        {operator.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <label className="checkboxRow">
                <input
                  type="checkbox"
                  checked={syncForm.dry_run}
                  onChange={(event) => setSyncForm({ ...syncForm, dry_run: event.target.checked })}
                />
                Dry run only
              </label>
              <div className="toolbar">
                <button className="buttonGhost" type="submit" disabled={actionLoading}>
                  {actionLoading ? "Running…" : "Reconcile"}
                </button>
              </div>
            </form>
          </div>

          <section className="resultPanel">
            <div className="panelHeader">
              <div>
                <h3>Latest Result</h3>
                <p>{actionTitle}</p>
              </div>
            </div>
            <pre>{actionPayload ? prettyJson(actionPayload) : "Run an action to inspect the structured result here."}</pre>
          </section>

          <section className="resultPanel">
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
                <span className={`pill ${selectedOperator.status === "active" ? "pillActive" : "pillInactive"}`}>
                  {selectedOperator.status}
                </span>
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
