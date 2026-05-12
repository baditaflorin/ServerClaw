# =============================================================================
# Multi-deployment lifecycle targets — ADR 0439, 0440, 0442
# =============================================================================
# This file is included from the main Makefile. It is purely additive in
# Phase 1: it does not change any existing target's behaviour. The
# `deployment=` parameter introduced here is consulted by Phase 2
# generators; until then, these targets only manage the deployment
# directory layout under .local/deployments/.
#
# Resolution precedence for `DEPLOYMENT` (matches ADR 0440):
#   1. `deployment=<slug>` on the command line
#   2. $DEPLOYMENT env var
#   3. .deployment marker in the current worktree
#   4. .local/active-deployment
# =============================================================================

PYTHON_DEPLOYMENT := uv run --quiet --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/deployment.py

# Resolve only when needed (so targets that don't require a deployment
# don't fail on a fresh checkout). Each consumer expands $(call deployment_resolve)
# at use-site.
deployment_resolve = $(or $(deployment),$(shell $(PYTHON_DEPLOYMENT) resolve --quiet 2>/dev/null))

# -----------------------------------------------------------------------------
# Lifecycle: create / select / inspect deployments
# -----------------------------------------------------------------------------

.PHONY: new-deployment
new-deployment:
	@if [ -z "$(slug)" ]; then \
	  echo "Usage: make new-deployment slug=<slug> apex=<domain> operator='Name <email>'"; \
	  exit 2; \
	fi
	@if [ -z "$(apex)" ]; then \
	  echo "ERROR: apex=<domain> is required (e.g. apex=acme.example)"; exit 2; \
	fi
	@target="$(LOCAL_OVERLAY_ROOT)/deployments/$(slug)"; \
	if [ -e "$$target" ]; then \
	  echo "ERROR: $$target already exists. Refusing to clobber."; exit 1; \
	fi; \
	echo "Scaffolding deployment $(slug) at $$target"; \
	mkdir -p "$$target/generated" "$$target/secrets" "$$target/receipts" "$$target/state"; \
	op_full="$(operator)"; \
	op_name=$$(printf '%s' "$$op_full" | sed 's/ *<.*//'); \
	op_email=$$(printf '%s' "$$op_full" | sed -n 's/.*<\(.*\)>.*/\1/p'); \
	if [ -z "$$op_name" ]; then op_name="Platform Operator"; fi; \
	if [ -z "$$op_email" ]; then op_email="operator@$(apex)"; fi; \
	{ \
	  echo "# Identity for deployment $(slug). ADR 0440."; \
	  echo "# Edit values below to match your deployment, then run:"; \
	  echo "#     make use-deployment slug=$(slug)"; \
	  echo "#     make whoami"; \
	  echo "---"; \
	  echo "platform_domain: $(apex)"; \
	  echo "platform_operator_email: $$op_email"; \
	  echo "platform_operator_name: \"$$op_name\""; \
	  echo "# hetzner_dns_zone_name: $(apex)"; \
	  echo "# hetzner_dns_zone_id: <fill from Hetzner DNS console>"; \
	  echo "# tailscale_tailnet: <fill from your Tailscale admin console>"; \
	  echo "platform_guest_network_cidr: 10.10.10.0/24"; \
	  echo "platform_tailscale_network_cidr: 100.64.0.0/10"; \
	} > "$$target/identity.yml"; \
	{ \
	  echo "# Topology for deployment $(slug). ADR 0440."; \
	  echo "# Replaces inventory/host_vars/proxmox-host.yml under the per-deployment layout."; \
	  echo "---"; \
	  echo "# host_public_ipv4: <Proxmox host's public IPv4>"; \
	  echo "# management_ipv4: <SSH target>"; \
	  echo "proxmox_guests: []"; \
	  echo "network_bridges: {}"; \
	} > "$$target/topology.yml"; \
	{ \
	  echo "# Service profile for deployment $(slug). ADR 0441."; \
	  echo "# Compose named profiles + per-deployment opt-ins/outs."; \
	  echo "---"; \
	  echo "profiles:"; \
	  echo "  - core"; \
	  echo "extra_services: []"; \
	  echo "disabled_services: []"; \
	  echo "service_overrides: {}"; \
	} > "$$target/profile.yml"; \
	echo ""; \
	echo "Created:"; \
	echo "  $$target/identity.yml   (edit apex, operator, DNS, network)"; \
	echo "  $$target/topology.yml   (edit proxmox host + guest list)"; \
	echo "  $$target/profile.yml    (pick service profiles)"; \
	echo ""; \
	echo "Next:"; \
	echo "  make use-deployment slug=$(slug)"; \
	echo "  make whoami"

.PHONY: use-deployment
use-deployment:
	@if [ -z "$(slug)" ]; then \
	  echo "Usage: make use-deployment slug=<slug>"; exit 2; \
	fi
	@target="$(LOCAL_OVERLAY_ROOT)/deployments/$(slug)"; \
	if [ ! -d "$$target" ]; then \
	  echo "ERROR: deployment $(slug) does not exist at $$target"; \
	  echo "Run: make new-deployment slug=$(slug) apex=<domain> operator='Name <email>'"; \
	  exit 1; \
	fi; \
	mkdir -p "$(LOCAL_OVERLAY_ROOT)"; \
	printf '%s\n' "$(slug)" > "$(LOCAL_OVERLAY_ROOT)/active-deployment"; \
	echo "Active deployment is now: $(slug)"

.PHONY: list-deployments
list-deployments:
	@$(PYTHON_DEPLOYMENT) list || true
	@count=$$($(PYTHON_DEPLOYMENT) list 2>/dev/null | wc -l | tr -d ' '); \
	if [ "$$count" = "0" ]; then \
	  echo "(no deployments yet — run 'make new-deployment slug=<slug> apex=<domain>')"; \
	fi

.PHONY: whoami
whoami:
	@$(PYTHON_DEPLOYMENT) whoami || true

.PHONY: bind-worktree
bind-worktree:
	@if [ -z "$(slug)" ]; then \
	  echo "Usage (run inside a .claude/worktrees/<name>/): make bind-worktree slug=<slug>"; \
	  exit 2; \
	fi
	@target="$(LOCAL_OVERLAY_ROOT)/deployments/$(slug)"; \
	if [ ! -d "$$target" ]; then \
	  echo "ERROR: deployment $(slug) does not exist."; exit 1; \
	fi; \
	if [ -f .git ]; then \
	  printf '%s\n' "$(slug)" > .deployment; \
	  echo "Worktree bound to deployment $(slug) (.deployment file written)"; \
	else \
	  echo "WARNING: this directory does not look like a git worktree (.git is not a file)."; \
	  echo "Writing .deployment anyway."; \
	  printf '%s\n' "$(slug)" > .deployment; \
	fi

.PHONY: validate-deployment
validate-deployment:
	@$(PYTHON_DEPLOYMENT) validate $(if $(slug),--slug $(slug),--all)

.PHONY: validate-all-deployments
validate-all-deployments:
	@$(PYTHON_DEPLOYMENT) validate --all

# -----------------------------------------------------------------------------
# ADR 0481 additions — agent-facing guard + legacy compatibility shim
# -----------------------------------------------------------------------------

# Alias for `list-deployments` so both spellings work.
.PHONY: deployments-list
deployments-list: list-deployments

# Refresh .local/identity.yml as a symlink to the active deployment's identity.
# Keeps the existing ~420 call sites that hardcode `.local/identity.yml`
# working without per-site changes. Run after `make use-deployment`.
.PHONY: sync-identity-link
sync-identity-link:
	@slug=$$($(PYTHON_DEPLOYMENT) resolve --quiet 2>/dev/null); \
	if [ -z "$$slug" ]; then \
	  echo "ERROR: no deployment resolved; cannot sync identity link" >&2; \
	  exit 2; \
	fi; \
	target="$(LOCAL_OVERLAY_ROOT)/deployments/$$slug/identity.yml"; \
	if [ ! -f "$$target" ]; then \
	  echo "ERROR: $$target does not exist" >&2; exit 2; \
	fi; \
	link="$(LOCAL_OVERLAY_ROOT)/identity.yml"; \
	if [ -L "$$link" ] || [ -f "$$link" ]; then rm -f "$$link"; fi; \
	ln -s "deployments/$$slug/identity.yml" "$$link"; \
	echo "Linked $$link -> deployments/$$slug/identity.yml"

# -----------------------------------------------------------------------------
# ADR 0482 — capacity-aware dynamic VM sizing
# -----------------------------------------------------------------------------

.PHONY: probe-capacity resolve-topology plan-capacity

probe-capacity: _require-deployment  ## Probe Proxmox host and write capacity.yml (read-only on remote).
	@slug=$$($(PYTHON_DEPLOYMENT) resolve --quiet); \
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/capacity_probe.py --slug "$$slug" --write

resolve-topology: _require-deployment  ## Resolve a per-VM topology from capacity + policy + profile and write topology.yml.
	@slug=$$($(PYTHON_DEPLOYMENT) resolve --quiet); \
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/resolve_topology.py --slug "$$slug" --write

plan-capacity: _require-deployment  ## Plan-only: show what the resolver would write without persisting.
	@slug=$$($(PYTHON_DEPLOYMENT) resolve --quiet); \
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/resolve_topology.py --slug "$$slug"

# -----------------------------------------------------------------------------
# ADR 0484 — self-verification contracts
# -----------------------------------------------------------------------------

.PHONY: self-check self-check-strict self-check-json detect-drift

self-check: _require-deployment  ## Run all post-conditions for the active deployment (skips bootstrap-only).
	@uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/self_check.py $(if $(step),--step $(step),) $(if $(tag),--tag $(tag),) $(if $(id),--id $(id),)

self-check-strict: _require-deployment  ## Same as self-check, but non-critical failures also exit non-zero.
	@uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/self_check.py --strict $(if $(step),--step $(step),) $(if $(tag),--tag $(tag),)

self-check-json: _require-deployment  ## Emit machine-readable JSON only.
	@uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/self_check.py --json $(if $(step),--step $(step),) $(if $(tag),--tag $(tag),)

lint-bootstrap-coverage:  ## (ADR 0484 §5) Verify every bootstrap step has ≥1 post-condition in post_conditions.yml.
	@uv run --with pyyaml python $(REPO_ROOT)/scripts/lint_bootstrap_coverage.py

detect-drift: _require-deployment  ## (ADR 0485) Run playbook --check and exit non-zero if changed > 0.
	@if [ -z "$(playbook)" ]; then \
	  echo "Usage: make detect-drift playbook=playbooks/harbor.yml [extra_vars='env=production']" >&2; \
	  exit 2; \
	fi
	@uv run --with pyyaml python $(REPO_ROOT)/scripts/detect_drift.py \
	  --playbook "$(playbook)" \
	  $(if $(extra_vars),--extra-vars "$(extra_vars)",) \
	  $(if $(slug),--slug "$(slug)",) \
	  $(if $(write_report),--write-report,)

# Internal guard target. Safety-critical wrappers (converge-*, live-apply-*,
# bootstrap, edge-publication, etc.) can list this as a prereq to fail loudly
# when no deployment is selected. Phase 2: retrofit existing wrappers; new
# wrappers MUST include this prereq.
.PHONY: _require-deployment
_require-deployment:
	@if ! $(PYTHON_DEPLOYMENT) resolve --quiet >/dev/null 2>&1; then \
	  echo "" >&2; \
	  echo "ERROR (ADR 0481): no deployment resolved." >&2; \
	  echo "Set one of:" >&2; \
	  echo "  - export DEPLOYMENT=<slug>" >&2; \
	  echo "  - make use-deployment slug=<slug>     # repo-wide default" >&2; \
	  echo "  - make bind-worktree slug=<slug>      # worktree-only" >&2; \
	  known=$$($(PYTHON_DEPLOYMENT) list 2>/dev/null | tr '\n' ' '); \
	  echo "Known: $${known:-(none yet)}" >&2; \
	  exit 2; \
	fi
