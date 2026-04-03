# ADR Discovery And Reservations

ADR 0325 moves ADR discovery from one ever-growing `.index.yaml` payload to a
compact root manifest plus shard-sized metadata files under `docs/adr/index/`.
It also adds `docs/adr/index/reservations.yaml` so parallel ADR-writing
workstreams can reserve number windows in the repo instead of coordinating
implicitly in chat.

## Generated Surfaces

- root manifest: `docs/adr/.index.yaml`
- range shards: `docs/adr/index/by-range/*.yaml`
- concern shards: `docs/adr/index/by-concern/*.yaml`
- implementation-status shards: `docs/adr/index/by-status/*.yaml`
- reservation ledger: `docs/adr/index/reservations.yaml`

## Refresh The Discovery Metadata

```bash
uv run --with pyyaml python3 scripts/generate_adr_index.py --write
```

Use `--check` in validation or CI when you need to confirm the committed root
manifest and shards are current:

```bash
./scripts/run_python_with_packages.sh pyyaml -- scripts/generate_adr_index.py --check
```

## Query ADRs Without Reading The Whole Corpus

Browse only the slice you need:

```bash
python3 scripts/adr_query_tool.py list --range 0300-0399
python3 scripts/adr_query_tool.py list --concern documentation
python3 scripts/adr_query_tool.py list --implementation-status Implemented
python3 scripts/adr_query_tool.py status-summary
```

Use `show`, `search`, or `affecting` when you need the canonical markdown
content after the shard lookup narrows the target.

## Reserve A Future ADR Window

1. Ask the allocator what the next free ADR number or window is:

```bash
python3 scripts/adr_query_tool.py allocate
python3 scripts/adr_query_tool.py allocate --window-size 5
```

2. Add an entry to `docs/adr/index/reservations.yaml` with:
   `id`, `start`, `end`, `reason`, `reserved_on`, and `status: active`.
   Optional fields: `owner`, `branch`, `workstream`, `expires_on`.

Example:

```yaml
schema_version: 1
reservations:
  - id: ws-0341-public-github-bundle
    start: "0341"
    end: "0345"
    owner: codex
    branch: codex/ws-0341-public-github-bundle
    workstream: ws-0341-public-github-bundle
    reason: Reserve the next documentation bundle before parallel ADR drafting
    reserved_on: 2026-04-03
    expires_on: 2026-04-10
    status: active
```

3. Regenerate the ADR discovery metadata:

```bash
uv run --with pyyaml python3 scripts/generate_adr_index.py --write
```

4. Verify the requested window is still conflict-free:

```bash
python3 scripts/adr_query_tool.py allocate --start 341 --end 345
```

If the command exits non-zero, the requested window overlaps an existing ADR or
an active reservation.

## Release Or Realize A Reservation

- when the reserved ADRs are committed, change `status` to `realized`
- when the workstream is cancelled or abandons the window, change `status` to
  `released` or `cancelled`
- regenerate the ADR discovery metadata after the ledger update

Active reservations are the only ones used for overlap checks and automatic
allocation.
