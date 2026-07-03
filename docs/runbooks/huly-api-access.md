# Huly — Programmatic API Access

Huly (self-hosted, `hardcoreeng/*` images) has no dashboard-generated API key
system. Programmatic access is a Node.js WebSocket/REST client package
(`@hcengineering/api-client`) plus a maintainer-provided admin CLI
(`hardcoreeng/tool`) for minting and managing service identities. This runbook
covers both, and the two message-driven automations built on top of them
(Telegram task bot, Gmail tag-based task creation).

Related role: `collections/ansible_collections/lv3/platform/roles/huly_runtime/`

---

## 1. What the sync integrations do (and don't do)

`huly-github-1`, `huly-gmail-1`, `huly-telegram-1` are **one-way visibility
bridges**, not task-creation triggers:

- **GitHub** — links a Huly project to a repo; issues/PRs appear as linked docs.
- **Gmail** — syncs a connected mailbox into Huly's Inbox for reading.
- **Telegram** — lets you chat with Telegram contacts inside Huly's Messenger.

None of them turn an incoming message into a Tracker issue automatically.
That's a separate automation layer, built on the API client — see §4 and §5.

---

## 2. The real API: `@hcengineering/api-client`

No REST/OpenAPI spec, no revocable key from a settings page. It's a
TypeScript/Node.js package with a WebSocket client (`connect`) and a REST
client (`connectRest`), authenticating as a Huly account (email/password or a
signed token) against a specific workspace.

### 2a. Install

All `@hcengineering/*` packages (including `api-client`) are published to the
public npmjs.org registry — no special registry config or token needed.

```bash
npm install @hcengineering/api-client@0.7.423 @hcengineering/core@0.7.423 \
            @hcengineering/tracker@0.7.423 @hcengineering/rank@0.7.423 ws
```

Pin the exact version to match the deployed `huly_version` (see role
defaults) — this repo runs the `v0.7.423` line. A caret range (`^0.7.3`) can
silently resolve to a newer client version than the server speaks.

### 2b. Connect with a token (preferred — see §3)

```ts
import { connect, NodeWebSocketFactory, type ConnectOptions } from '@hcengineering/api-client'

const client = await connect('https://huly.example.com', {
  token: process.env.HULY_TOKEN!,
  workspace: process.env.HULY_WORKSPACE!,
  socketFactory: NodeWebSocketFactory,
  connectionTimeout: 30000
} satisfies ConnectOptions)
```

### 2c. Create a task (Tracker issue)

```ts
import core, { generateId, SortingOrder, type Ref } from '@hcengineering/core'
import { makeRank } from '@hcengineering/rank'
import tracker, { type Issue, IssuePriority } from '@hcengineering/tracker'

const project = await client.findOne(tracker.class.Project, { identifier: 'PROJ' })
const issueId: Ref<Issue> = generateId()

const inc = await client.updateDoc(tracker.class.Project, core.space.Space, project._id, { $inc: { sequence: 1 } }, true)
const sequence = (inc as any).object.sequence

const lastOne = await client.findOne<Issue>(tracker.class.Issue, { space: project._id }, { sort: { rank: SortingOrder.Descending } })
const description = await client.uploadMarkup(tracker.class.Issue, issueId, 'description', '# Task body', 'markdown')

await client.addCollection(tracker.class.Issue, project._id, project._id, project._class, 'issues', {
  title: 'Task title',
  description,
  status: project.defaultIssueStatus,
  number: sequence,
  kind: tracker.taskTypes.Issue,
  identifier: `${project.identifier}-${sequence}`,
  priority: IssuePriority.Urgent,
  assignee: null, component: null, estimation: 0, remainingTime: 0,
  reportedTime: 0, reports: 0, subIssues: 0, parents: [], childInfo: [], dueDate: null,
  rank: makeRank(lastOne?.rank, undefined)
}, issueId)
```

---

## 3. "API keys" — the actual mechanism (`hardcoreeng/tool`)

Huly ships an admin CLI image, `hardcoreeng/tool:${HULY_VERSION}`, that talks
directly to the account DB and mints signed JWTs (`generate-token`). This is
the closest thing to an API key: no password needed at runtime, and it's what
Huly's own migration/ops tooling uses internally.

It must run on the `huly_net` docker network, on the same host as the stack
(`docker-runtime-lv3` in this deployment), with the instance's `SECRET` from
the rendered `.env`.

### 3a. Create a dedicated automation account

Never reuse a personal login for a bot — create a separate member so access
can be reasoned about (and downgraded) independently:

```bash
scripts/huly-automation/create-account.sh automation@example.com 'Automation' 'Bot' '<password>' <workspace-slug>
```

This runs (on the guest, inside `huly_net`):
```bash
docker run --rm --network huly_huly_net \
  -e SERVER_SECRET="$SECRET" -e ACCOUNTS_URL="http://account:3000" \
  -e TRANSACTOR_URL="ws://transactor:3333" -e DB_URL="$CR_DB_URL" \
  -e ACCOUNT_DB_URL="$CR_DB_URL" -e QUEUE_CONFIG="redpanda:9092" \
  -e STORAGE_CONFIG="minio|minio?accessKey=minioadmin&secretKey=minioadmin" \
  hardcoreeng/tool:${HULY_VERSION} -- bundle.js create-account <email> -p <password> -f <first> -l <last>

# then assign to the workspace:
docker run ... hardcoreeng/tool:${HULY_VERSION} -- bundle.js assign-workspace <email> <workspace>
```

### 3b. Mint a token for it (the "API key")

```bash
scripts/huly-automation/generate-token.sh automation@example.com <workspace-slug>
```
Prints a JWT to stdout. Use it as `token` in `connect()` (§2c) — no password
transmitted at runtime. Regenerate any time; old tokens keep working until
revoked (§3c) or the instance `SECRET` rotates.

### 3c. Revoke

There is **no single-token revocation list** in this Huly version — JWTs are
stateless, verified only against the instance `SECRET` and re-checked for
workspace role on every request. Two real levers:

- **Soft revoke (targeted, immediate):** downgrade the automation account's
  role to the lowest privilege. Authorization is re-derived from the DB per
  request, so this takes effect for already-issued tokens too:
  ```bash
  scripts/huly-automation/revoke-account.sh automation@example.com <workspace-slug>
  ```
  (runs `set-user-role <email> <workspace> DocGuest`)

- **Hard revoke (nuclear, fleet-wide):** rotate the instance `SECRET`. This
  invalidates **every** token and logs out **every** user, not just the bot.
  Only for genuine compromise:
  ```bash
  scripts/huly-automation/rotate-secret.sh   # requires explicit confirmation
  ```

There is no CLI command to delete a member account outright in this Huly
version (`drop-account` is present in source but disabled). To fully remove
membership, use Huly's own UI: **Settings → Members → remove**.

---

## 4. Telegram: "check my tasks" / "add a task" via chat

Not built into `huly-telegram-1` (that container just bridges your personal
Telegram DMs into Huly's Messenger via MTProto). A command bot needs its own,
**separate** Telegram bot (a second BotFather bot) so it doesn't compete for
updates with the one already wired into the stack.

Design: a small long-polling Node service, using the same `@hcengineering/api-client`
token from §3b, mapped: `/tasks` → list open issues assigned to the automation
account; any other text → create a new issue with that text as the title.
Restrict to an allow-listed Telegram user ID (yours) so randoms can't file
issues into your tracker.

See `collections/ansible_collections/lv3/platform/roles/huly_runtime/files/task-bot/`
for the implementation, activated by `.local/huly/task-bot-credentials.yml`
(`telegram_bot_token`, `allowed_user_id`, `project_identifier`) together with
`.local/huly/automation-credentials.yml` (`token`, `workspace`).

---

## 5. Gmail: tag-based task creation ("[tag] in subject → task")

Not built into `huly-gmail-1` either (that's inbox visibility sync only).
This is a standalone watcher that:

1. Pulls new-message notifications from the Pub/Sub subscription created
   alongside `huly-gmail-watch` (a **pull** subscription — no public webhook
   needed).
2. Fetches each new message's headers via the Gmail API.
3. Matches the subject against a configurable list of `{ pattern, project }`
   rules (not hardcoded to one team/tag) — e.g. `[veld]` → the `VELD`
   project, `[ops]` → `OPS`, a fallback default project for unmatched-but-flagged
   mail, or no match → ignored.
4. Creates the Tracker issue via the API client (§2d).

Requires its own one-time OAuth consent (separate refresh token from the one
`huly-gmail-1` holds internally) — see
`collections/ansible_collections/lv3/platform/roles/huly_runtime/files/gmail-task-watcher/README.md`
for the one-time `authorize` step.

Config lives in `.local/huly/gmail-task-rules.json`:
```json
{
  "rules": [
    { "pattern": "[veld]", "project": "VELD" },
    { "pattern": "[ops]", "project": "OPS" }
  ]
}
```

### 5a. One-time setup
1. GCP service account with `roles/pubsub.subscriber` on the `huly-gmail-watch-sub`
   subscription — key file at `.local/huly/gmail-watcher-service-account.json`.
2. A dedicated OAuth client (Desktop app type, so it can use the loopback
   redirect flow) — separate from the Web-application client `huly-gmail-1`
   already uses, so nothing here can affect that live integration.
3. Run the one-time authorize step **locally, with a browser**:
   ```bash
   cd collections/ansible_collections/lv3/platform/roles/huly_runtime/files/gmail-task-watcher
   npm install
   node authorize.js /path/to/client_secret_....json
   ```
   Save the printed refresh token to `.local/huly/gmail-watcher-refresh-token`.
