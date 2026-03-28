# Capacity Classes

## Purpose

ADR 0192 separates spare capacity into protected classes so preview, recovery, and standby workflows stop competing through one opaque shared pool.

## Repo Surfaces

- [config/capacity-model.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/capacity-model.json)
- [docs/schema/capacity-model.schema.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/schema/capacity-model.schema.json)
- [scripts/capacity_report.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/capacity_report.py)
- [scripts/fixture_manager.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/fixture_manager.py)
- [scripts/restore_verification.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/restore_verification.py)

## Classes

- `ha_reserved`: protected standby and failover headroom
- `recovery_reserved`: protected restore-drill and disaster-recovery headroom
- `preview_burst`: protected local burst capacity for fixtures, previews, and replay tests

## Commands

Render the operator report with class summaries:

```bash
make capacity-report NO_LIVE_METRICS=true
make capacity-report
make capacity-report FORMAT=json NO_LIVE_METRICS=true
```

Check whether a preview request fits its class without break-glass:

```bash
uv run --with pyyaml python scripts/capacity_report.py \
  --check-class-request \
  --requester-class preview \
  --proposed-change 4,2,32
```

Check whether a declared restore drill can use recovery capacity and preview spillover:

```bash
uv run --with pyyaml python scripts/capacity_report.py \
  --check-class-request \
  --requester-class restore-verification \
  --declared-drill \
  --proposed-change 4,2,48
```

Check a bounded break-glass request before borrowing `ha_reserved`:

```bash
uv run --with pyyaml python scripts/capacity_report.py \
  --check-class-request \
  --requester-class preview \
  --proposed-change 12,6,80 \
  --break-glass-ref CHG-0192-EXAMPLE \
  --duration-hours 2
```

Inspect current preview occupancy from active fixture receipts and cluster state:

```bash
uv run --with pyyaml python scripts/fixture_manager.py list --no-refresh-health
```

## Admission Rules

- Preview and fixture demand must remain within `preview_burst` during normal operation.
- Recovery drills may borrow from `preview_burst` only when the drill is explicitly declared.
- Borrowing from `ha_reserved` requires a concrete break-glass reference and a positive duration bound.
- When the auxiliary cloud domain is available, preview demand should spill there before any protected local class is borrowed.

## Automation Notes

- `scripts/fixture_manager.py` now accepts both the legacy top-level `ephemeral_pool` shape and the reservation-backed `preview_burst` shape, but the canonical repo truth is the reservation-backed model.
- `scripts/restore_verification.py` checks `recovery_reserved` before starting any destructive restore workflow so the drill fails fast when protected recovery headroom is missing.
- `scripts/capacity_report.py --format json` is the machine-readable source for class totals, occupancy, and remaining headroom.
