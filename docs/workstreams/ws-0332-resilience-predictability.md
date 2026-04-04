# Workstream ws-0332-resilience-predictability: Compose Dependency Health Gates

- ADR: [ADR 0346](../adr/0346-compose-dependency-health-gates-as-a-repo-enforced-resilience-baseline.md)
- Title: enforce health-gated compose dependencies for more predictable service recovery
- Status: live_applied
- Included In Repo Version: not yet
- Branch-Local Receipt: `receipts/live-applies/2026-04-04-adr-0346-compose-dependency-health-gates-live-apply.json`
- Implemented On: 2026-04-04
- Live Applied On: 2026-04-04
- Live Applied In Platform Version: 0.130.98
- Latest Verified Base: `origin/main@20a66bbf0` (`repo 0.178.3`, `platform 0.130.98`)
- Branch: `codex/ws-0332-live-apply-r1`
- Worktree: `.worktrees/ws-0332-live-apply`
- Owner: codex
- Depends On: `ADR 0064`, `ADR 0107`, `ADR 0204`, `ADR 0246`, `ADR 0319`
- Conflicts With: none

## Scope

- turn compose dependency health gates into an explicit repository contract instead of an ad hoc role-by-role convention
- extend service completeness so compose services with local dependencies must either declare a health-gated startup path or carry a time-bounded suppression
- fix the safe runtime templates that still used blind dependency startup ordering
- document the remaining bounded exception where the upstream image does not yet expose a safe in-container health probe path

## Planned Outcome

- `scripts/service_completeness.py` will fail compose services that use `depends_on` without a matching `condition: service_healthy` gate unless the gap is explicitly time-boxed in `config/service-completeness.json`.
- `dozzle`, `minio`, and `searxng` will converge with health-gated local dependencies in their compose templates.
- `platform_context_api` will carry an explicit short-lived suppression until the Qdrant image path is given a safe governed health probe contract.
- `docs/runbooks/compose-runtime-resilience.md` will explain how to verify, fix, or time-box dependency gating gaps so future outages do not reintroduce the same startup races silently.

## Outcome

- `scripts/service_completeness.py` now enforces `Dependency health gate` for compose services that declare `depends_on`, which makes blind startup ordering a repository-visible contract violation.
- `dozzle`, `minio`, and `searxng` now ship health-gated dependency startup in their compose templates.
- `platform_context_api` is explicitly time-boxed through `2026-05-15` while the current Qdrant image path still lacks a safe governed in-container health probe contract.
- `docs/runbooks/compose-runtime-resilience.md` captures the operator path for validating, fixing, or time-boxing future dependency-gating gaps.

## Verification

- `python3 scripts/validate_service_completeness.py --validate`
- `python3 scripts/validate_service_completeness.py --service dozzle --service minio --service platform_context_api --service searxng`
- `uv run --with pytest --with pyyaml python -m pytest -q tests/test_validate_service_completeness.py tests/test_dozzle_runtime_role.py tests/test_minio_runtime_role.py tests/test_searxng_runtime_role.py`
- `make syntax-check-dozzle`
- `make syntax-check-minio`
- `make syntax-check-searxng`
- `python3 scripts/workstream_registry.py --check`
- `uv run --with pyyaml python3 scripts/workstream_surface_ownership.py --validate-registry`
- `uv run --with pyyaml python3 scripts/workstream_surface_ownership.py --validate-branch --base-ref origin/main`
- `uv run --with pyyaml python3 scripts/generate_discovery_artifacts.py --check`
- `uv run --with pyyaml python3 scripts/validate_public_entrypoints.py --check`

## Live Apply Evidence

- `receipts/live-applies/evidence/2026-04-04-ws-0332-minio-runtime-resume-r2.txt` and `receipts/live-applies/evidence/2026-04-04-ws-0332-minio-edge-public-r2.txt` show the bounded MinIO replay from the latest realistic `origin/main` base plus the green API and authenticated console checks.
- `receipts/live-applies/evidence/2026-04-04-ws-0332-dozzle-runtime-check-r3.txt` and `receipts/live-applies/evidence/2026-04-04-ws-0332-dozzle-verification-r2.txt` show the Dozzle hub health, local plus remote agent reachability, and the shared OIDC redirect path at `https://logs.lv3.org/`.
- `receipts/live-applies/evidence/2026-04-04-ws-0332-searxng-runtime-resume-r4.txt` and `receipts/live-applies/evidence/2026-04-04-ws-0332-searxng-verification-r2.txt` show the SearXNG runtime JSON endpoint, the Proxmox host proxy, the tailnet DNS hostname, and the Open WebUI web-search environment wiring.

## Live Apply Notes

- A fresh exact-main worktree needed `make generate-edge-static-sites` before the shared `nginx_edge_publication` role could publish the docs and changelog portals; that committed generation step is preserved as evidence instead of being hidden as an ad hoc prerequisite.
- The first full MinIO replay stalled under shared `docker-runtime-lv3` memory pressure even though `nftables` was already installed and active, so the final proof set resumes from the first safe service-local task rather than pretending the initial replay was green.
- The Dozzle replay reached green service verification before the shared post-verify Syft SBOM scan saturated `docker-runtime-lv3`; that non-critical host-wide scan was intentionally stopped, and the explicit Dozzle runtime plus edge verification reruns are the final proof points.
- The SearXNG runtime itself replayed and verified successfully, but a mid-play resume into the downstream `open_webui_runtime` role is not restart-safe because earlier registered variables are skipped. The final proof set therefore keeps the successful SearXNG runtime replay and an explicit Open WebUI environment verification instead of masking the bounded resume limitation.

## Exact-Main Integration Status

- Branch-local live apply is complete from `origin/main@20a66bbf0`; the remaining exact-main step is limited to merging this receipt and the canonical-truth metadata onto `main`.
- `VERSION`, `changelog.md`, `README.md`, and `versions/stack.yaml` remain untouched in this worktree until the exact-main integration step is replayed and revalidated.
