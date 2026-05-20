# =============================================================================
# Bootstrap + capacity-aware sizing + self-verification + drift detection
# ADR 0482 / 0483 / 0484 / 0485 (single deployment per repo — ADR 0488)
# =============================================================================
# Included from the main Makefile. Each repo checkout configures exactly one
# deployment via `.local/identity.yml`; no slug threading needed.
# =============================================================================

# -----------------------------------------------------------------------------
# ADR 0482 — capacity-aware dynamic VM sizing
# -----------------------------------------------------------------------------

.PHONY: derive-deployment-files derive-host-vars probe-capacity resolve-topology plan-capacity

derive-deployment-files:  ## (ADR 0483 §3 step 0) Emit identity.yml/connection.yml/profile.yml from .local/manifest.yml.
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/derive_deployment_files.py

derive-host-vars:  ## (ADR 0488) Probe the Proxmox host's network config and write .local/host_vars/proxmox-host.yml.
	uv run --with pyyaml python $(REPO_ROOT)/scripts/derive_host_vars.py --write

probe-capacity:  ## (ADR 0482 + 0488) Probe Proxmox host (from .local/identity.yml) and write .local/capacity.yml.
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/capacity_probe.py --write

resolve-topology:  ## (ADR 0482 + 0488) Resolve a per-VM topology from capacity + policy + profile and write .local/topology.yml.
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/resolve_topology.py --write

plan-capacity:  ## (ADR 0482 + 0488) Plan-only: show what the resolver would write without persisting.
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/resolve_topology.py

# -----------------------------------------------------------------------------
# ADR 0484 — self-verification contracts
# -----------------------------------------------------------------------------

.PHONY: self-check self-check-strict self-check-json self-check-final-smoke lint-bootstrap-coverage write-bootstrap-receipt

self-check:  ## Run all post-conditions for the deployment (reads .local/identity.yml).
	@uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/self_check.py $(if $(step),--step $(step),) $(if $(tag),--tag $(tag),) $(if $(id),--id $(id),)

self-check-final-smoke:  ## Run only final-smoke tagged post-conditions (used by bootstrap step 12).
	@$(MAKE) self-check tag=final-smoke

self-check-strict:  ## Same as self-check, but non-critical failures also exit non-zero.
	@uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/self_check.py --strict $(if $(step),--step $(step),) $(if $(tag),--tag $(tag),)

self-check-json:  ## Emit machine-readable JSON only.
	@uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/self_check.py --json $(if $(step),--step $(step),) $(if $(tag),--tag $(tag),)

lint-bootstrap-coverage:  ## (ADR 0484 §5) Verify every bootstrap step has ≥1 post-condition in post_conditions.yml.
	@uv run --with pyyaml python $(REPO_ROOT)/scripts/lint_bootstrap_coverage.py

write-bootstrap-receipt:  ## Write the bootstrap completion receipt to receipts/live-applies/ (bootstrap step 13).
	@uv run --with pyyaml python $(REPO_ROOT)/scripts/write_bootstrap_receipt.py

# -----------------------------------------------------------------------------
# ADR 0483 — hands-off bootstrap orchestrator
# -----------------------------------------------------------------------------

.PHONY: bootstrap bootstrap-resume bootstrap-status bootstrap-dry-run

bootstrap:  ## (ADR 0483) Run the full 14-step bootstrap chain. Pass resume-from=<step-id> to skip earlier steps.
	@uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/bootstrap_orchestrator.py \
	  $(if $(resume-from),--resume-from "$(resume-from)",) \
	  $(if $(resume_last),--resume-last,)

bootstrap-resume:  ## Resume bootstrap from last failed step (reads last failure receipt).
	@uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/bootstrap_orchestrator.py --resume-last

bootstrap-status:  ## Print status of the last bootstrap run from receipt.
	@uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/bootstrap_orchestrator.py --status

bootstrap-dry-run:  ## Print which steps would run without invoking make targets.
	@uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/bootstrap_orchestrator.py \
	  $(if $(resume-from),--resume-from "$(resume-from)",) \
	  --dry-run

# -----------------------------------------------------------------------------
# ADR 0485 — convergence idempotency / drift detection
# -----------------------------------------------------------------------------

.PHONY: detect-drift

detect-drift:  ## (ADR 0485) Run playbook --check and exit non-zero if changed > 0.
	@if [ -z "$(playbook)" ]; then \
	  echo "Usage: make detect-drift playbook=playbooks/harbor.yml [extra_vars='env=production']" >&2; \
	  exit 2; \
	fi
	@uv run --with pyyaml python $(REPO_ROOT)/scripts/detect_drift.py \
	  --playbook "$(playbook)" \
	  $(if $(extra_vars),--extra-vars "$(extra_vars)",) \
	  $(if $(write_report),--write-report,)
