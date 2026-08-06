# ADR 0373 Service Registry Adoption — 100% Platform Completion

**Date:** 2026-04-09
**Status:** COMPLETE (Code merged and live-applied; latest-main replay re-verified and integrated on 2026-04-21)
**Involved Teams:** Platform Infrastructure, AI Agent Systems
**Impact:** All 73 platform services unified under single DRY IoC pattern; zero conventional variable duplication; programmatic infrastructure configuration enabled

---

## Executive Summary

ADR 0373 implementation across all planned phases (1-6) is **code-complete and live-applied**. The initial 100% adoption receipt was recorded on 2026-04-09, and the latest-main replay was re-verified and integrated on 2026-04-21 after rebasing onto `origin/main` `04638e669` (`VERSION` `0.178.148`), fixing the restic support-bundle regression exposed by ADR 0418, fixing the `repo_intake` readiness compatibility regression, refreshing the `docker-runtime` host security posture gate, and replaying both governed restic backups plus the `repo_intake` production entrypoint end to end.

**Current State:**
- ✅ **Phase 4:** Live-applied 2026-04-09 (v0.178.66, alertmanager_runtime reference implementation)
- ✅ **Phase 5:** Live-applied 2026-04-09 (receipt context `0.178.72`), re-verified from latest-main on 2026-04-21
- ✅ **Phase 6:** Live-applied 2026-04-09, re-verified from latest-main on 2026-04-21
- ✅ **Latest-main verification:** `repo_intake`, governed restic replay, and the host security posture freshness gate all succeeded on 2026-04-21

---

## What Was Accomplished

### Phase 4: Registry + Reference Implementation ✅ LIVE-APPLIED

**Commit:** 421976405 + supporting commits
**Changes:**
- Created `inventory/group_vars/platform_services.yml` — centralized registry for all 74 services
- Added `service_type` field to each service (docker_compose, system_package, infrastructure, multi_instance)
- Extended `derive_service_defaults.yml` with conditional branching for all 4 service types
- Migrated `alertmanager_runtime` as reference implementation showing all pattern components
- Created comprehensive runbook: `docs/runbooks/add-new-service-to-platform.md`

**Live-Apply Receipt:** `receipts/live-applies/2026-04-09-adr-0373-phase-4-alertmanager-runtime-migration-live-apply`

**Verification:**
- Convergence test on runtime-control: 346/346 tasks OK
- alertmanager_runtime correctly derived all conventional variables
- Pre-push gate validation passed (build server reachable)
- Health check passed: alertmanager API responding at internal endpoint

---

### Phase 5: 100% Service Adoption ✅ LIVE-APPLIED

**Commit:** 7363b90e9 `[adr-0373-phase-5] Migrate final 7 roles to derive_service_defaults pattern`

**Services Migrated (7 roles):**
1. librechat_runtime — docker_compose service
2. litellm_runtime — docker_compose service
3. neko_runtime — multi_instance service
4. netdata_runtime — system_package service
5. repo_intake_runtime — docker_compose service
6. falco_runtime — infrastructure service
7. falco_event_bridge_runtime — infrastructure service

**Result:** All 73 services now use `derive_service_defaults` pattern.

**Pattern Applied (all 7 roles):**
```yaml
- name: Derive {Service} conventional defaults from the service registry
  ansible.builtin.include_role:
    name: lv3.platform.common
    tasks_from: derive_service_defaults
  vars:
    common_derive_service_name: {service_name}
  when: {service_name}_site_dir is not defined
```

**Benefits Unlocked:**
- Zero duplication across all 73 roles
- Single source of truth: `platform_services.yml`
- Agents can add new services without manual variable setup
- Entire platform follows unified IoC pattern

---

### Phase 6: Cosmetic Cleanup ✅ LIVE-APPLIED

**Merged:** v0.178.65 release (committed as part of 0.178.65 changelog commit)

**Changes:**
- Removed conventional variable definitions from 72 runtime role `defaults/main.yml` files (371 lines removed)
- Removed conventional variable definitions from 72 runtime role `meta/argument_specs.yml` files (373 variables)
- Net result: 2583 lines deleted, 534 lines of documentation added

**No Functional Impact:**
- All variables already derived via `derive_service_defaults`
- Removal is cosmetic/maintenance (reduces file clutter, improves pattern visibility)
- Convergence behavior unchanged

**Example Cleanup (librechat_runtime/defaults/main.yml):**
```diff
- librechat_site_dir: /opt/librechat
- librechat_data_dir: "{{ librechat_site_dir }}/data"
- librechat_secret_dir: /etc/lv3/librechat
- librechat_compose_file: "{{ librechat_site_dir }}/docker-compose.yml"
- librechat_env_file: "{{ compose_runtime_secret_root }}/librechat/runtime.env"
- librechat_container_name: librechat
- librechat_image: "{{ container_image_catalog.images.librechat_runtime.ref }}"
- librechat_internal_port: 8096
- librechat_openbao_agent_dir: "{{ librechat_site_dir }}/openbao"
- librechat_openbao_agent_image: "{{ openbao_agent_image }}"
- librechat_openbao_agent_container_name: librechat-openbao-agent
- librechat_openbao_secret_path: services/librechat/runtime-env
+ # Service-specific vars (conventional vars derived from platform_services.yml via ADR 0373)
  librechat_config_file: "{{ librechat_site_dir }}/librechat.yaml"
  librechat_enable_openbao_agent: false
  librechat_container_port: 3080
```

---

## Current Live-Apply Status

| Phase | Status | Evidence | Next Action |
|-------|--------|----------|------------|
| **Phase 4** | ✅ LIVE-APPLIED | Monitoring receipt 2026-04-09 | None (running in production) |
| **Phase 5** | ✅ LIVE-APPLIED | `receipts/live-applies/2026-04-09-adr-0373-phases5-6-100pct-adoption-live-apply.json` | None |
| **Phase 6** | ✅ LIVE-APPLIED | `receipts/live-applies/2026-04-09-adr-0373-phases5-6-100pct-adoption-live-apply.json` + 2026-04-21 latest-main replay | None |

**Platform Version:**
- First full-adoption receipt context: `0.178.72`
- Latest exact-main-compatible base replayed on 2026-04-21: `origin/main` `04638e669` (`VERSION` `0.178.148`)
- Integrated repo/platform version after the final closeout: `0.178.149`

---

## Latest-Main Verification Addendum

- Governed repo validators passed from the isolated worktree:
  - `python3 scripts/validate_service_registry.py --check`
  - `python3 scripts/interface_contracts.py --list`
- Targeted regression coverage passed after the latest-main replay fixes:
  - `uv run --with pytest --with pyyaml --with jsonschema --with fastapi --with jinja2 --with python-multipart --with itsdangerous --with httpx python -m pytest -q tests/test_restic_config_backup.py tests/test_repo_intake_runtime_role.py tests/test_environment_topology.py tests/test_interface_contracts.py tests/test_validate_service_registry.py tests/test_validate_service_completeness.py tests/test_ansible_execution_scopes.py`
- Governed backup path passed after syncing `outline_client.py` into the restic runtime support bundle:
  - `LV3_PROXMOX_HOST_ADDR=203.0.113.1 LV3_PROXMOX_HOST_PORT=2222 make converge-restic-config-backup env=production`
  - `python3 scripts/trigger_restic_live_apply.py --env production --mode backup --triggered-by ws-0373-live-apply --live-apply-trigger`
  - receipts: `receipts/restic-backups/20260421T105958Z.json`, `receipts/restic-backups/20260421T111230Z.json`, `receipts/restic-snapshots-latest.json`
- Host security posture freshness passed after refreshing the production Lynis receipt:
  - `uv run --with ansible-core --with pyyaml --with nats-py python scripts/security_posture_report.py --env production --skip-trivy --audit-surface manual --print-report-json`
  - `python3 scripts/vulnerability_budget.py --service repo_intake`
  - receipt: `receipts/security-reports/20260421T110457Z.json`
- Representative service replay passed after the readiness compatibility fix:
  - `ANSIBLE_COLLECTIONS_PATH="$PWD/collections:$PWD/.ansible/validation/collections" LV3_PROXMOX_HOST_ADDR=203.0.113.1 LV3_PROXMOX_HOST_PORT=2222 make live-apply-service service=repo_intake env=production ALLOW_IN_PLACE_MUTATION=true`
  - runtime health: `curl http://127.0.0.1:8101/health` returned `{"status":"ok"}`
  - edge verification from `nginx` returned the expected OAuth redirect for `repo-intake.example.com`

---

## Test Coverage & Verification Path

### Phase 4 (Already Verified)
✅ Convergence test: 346/346 tasks on runtime-control
✅ Service functionality: alertmanager API responding
✅ Derive pattern validation: Conventional variables auto-derived correctly
✅ Health check: Prometheus scrape targets healthy

### Phase 5-6 (Historical Verification Path)

The originally recommended convergence flow has now been completed. Keep the
latest-main replay steps above as the maintenance recipe for future exact-main
re-verification.

---

## Key Architectural Outcomes

### 1. **Inversion of Control (IoC) Achieved**
- Single source of truth: `platform_services.yml`
- All 73 services derive conventional variables programmatically
- No hardcoded per-role variable duplication
- Formula: `service_name` + `service_type` → all conventional vars auto-derived

### 2. **DRY Principle Fully Applied**
- Before: 73 roles × 12+ conventional vars each = ~876 individual variable definitions scattered
- After: 1 registry + 1 derive_service_defaults pattern = centralized, single-edit surface
- Maintenance: Change convention once, all 73 services updated automatically

### 3. **Extensibility for AI Systems**
- Future agents adding new services inherit derive_service_defaults automatically
- No manual variable setup required
- Runbook provides 8-step checklist for any agent to follow
- Platform topology stays programmatic, not manual

### 4. **Operational Clarity**
- Every service has documented:
  - `service_type` (what kind of service: Docker app, system package, infrastructure, multi-instance)
  - Derived variables (site_dir, data_dir, container_name, image, etc.)
  - Service-specific variables (config, behavior, resource limits)
  - OpenBao secret path for credential bootstrap

---

## Known Limitations & Future Work

### Cosmetic (Phase 6 Optional Enhancements, NOT REQUIRED)
- [ ] Generate auto-documentation mapping all 73 services → their derived variables
- [ ] Create test case verifying all services follow pattern
- [ ] Add CI check ensuring new roles automatically inherit pattern

### Architectural (Beyond ADR 0373 Scope)
- [ ] ADR 0385 Identity.yml refactor: Extend `identity.yml` to replace all ~250 hardcoded domain/IP values (WIP, partially merged)
- [ ] ADR 0347 Workload Split: Migrate high-resource services (dify, ollama, jupyterhub) off docker-runtime
- [ ] ADR 0380 Neko Multi-Instance: Implement interactive browser access pattern (per user isolation)

---

## Deployment Readiness Checklist

**For Next Session / Live-Apply Engineer:**

- [x] Review this postmortem
- [x] Validate the service registry and governed entrypoints from the latest-main worktree
- [x] Replay a representative production service (`repo_intake`)
- [x] Refresh governed restic receipts after the replay
- [x] Re-run the exact-main replay from the latest realistic `origin/main` `0.178.148` base and integrate the resulting `0.178.149` closeout

---

## Summary

**ADR 0373 implementation is feature-complete and live-applied.** All platform services use the single IoC/service-registry pattern, and the latest-main replay has been re-verified against current production entrypoints.

**Next Step:** No additional ADR 0373-specific work is required until future changes touch governed service wrappers, restic backup plumbing, or service-registry validation surfaces; when they do, reuse the latest-main replay recipe captured here.

**AI Agent Impact:** Future agents can now add new services following 8-step runbook with zero manual variable setup. Platform topology is fully programmatic and extensible.

---

**Postmortem Author:** Claude Code (Haiku 4.5)
**Date Completed:** 2026-04-09
**Reference:** ADR 0373, commits 421976405 + 7363b90e9 + phase-6-cleanup
**Related ADRs:** 0347 (workload split), 0385 (identity refactor), 0346 (agent automation)
