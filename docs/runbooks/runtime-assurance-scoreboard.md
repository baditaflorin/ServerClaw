# Runtime Assurance Scoreboard

## Purpose

Use the interactive ops portal scoreboard to answer one operator question
quickly and honestly:

Which active services in which environments are safe to trust right now?

## Entry Surface

- interactive portal: `https://ops.lv3.org`
- section: `Platform Overview` -> `Runtime Assurance`

The scoreboard is rendered from the repo-synced service catalog, publication
registry, live-apply receipts, and the current gateway-backed
`/v1/platform/health` payload.

## What The Rollup Means

Each active service-environment row carries:

- overall rollup state
- per-dimension assurance state
- last verified timestamp per dimension
- owning team
- service runbook link
- next action when one required dimension is not green

The current dimensions are:

- `Existence` — current runtime witness from the health-composite path
- `Runtime` — current health-composite rollup
- `Route` — declared publication truth plus live route witness when available
- `Auth` — protected browser journey proof when required
- `TLS` — dedicated HTTPS or TLS assurance evidence when required
- `Logs` — central log-ingestion and queryability proof when required
- `Smoke` — latest matched stage-scoped live-apply or smoke receipt

## State Rules

- `pass` means the dimension has direct matched evidence
- `degraded` means partial or indirect evidence exists, but the dedicated proof
  is still missing or impaired
- `failed` means the current live evidence contradicts the declared truth
- `unknown` means the portal cannot find enough evidence yet
- `n/a` means the dimension is not required for that surface

Only required dimensions participate in the overall row state.

The rollup never treats `unknown` as healthy.

## Operator Workflow

1. Open `ops.lv3.org` and review the `Runtime Assurance` summary counts.
2. Start with rows whose overall state is `failed`, then `degraded`, then
   `unknown`.
3. Read the per-dimension detail and `Next Action` column for the first red or
   missing proof.
4. Follow the linked service runbook before mutating the live surface.
5. After a converge or repair, refresh the overview and confirm the row moved
   with new evidence timestamps.

## Verification

From `docker-runtime-lv3`:

```bash
curl -sf http://127.0.0.1:8092/partials/overview | grep -F "Runtime Assurance"
```

From an operator browser:

- the overview shows the `Runtime Assurance` section
- at least one active service row is present
- each row exposes a runbook link and next action

## Notes

- this scoreboard is intentionally conservative: if the evidence is missing, the
  rollup should stay `unknown` or `degraded` instead of optimistic green
- a green scoreboard row does not replace logs, receipts, or runbooks; it only
  tells you which proof sources are currently aligned
