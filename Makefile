REPO_ROOT := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
LOCAL_OVERLAY_ROOT ?= $(shell $(REPO_ROOT)/scripts/resolve_local_overlay_root.sh)
ANSIBLE_INVENTORY := $(REPO_ROOT)/inventory/hosts.yml
BOOTSTRAP_KEY ?= $(LOCAL_OVERLAY_ROOT)/ssh/bootstrap.id_ed25519
ANSIBLE_LOCAL_TEMP ?= /tmp/platform_server-ansible-local
ANSIBLE_REMOTE_TEMP ?= /tmp
ANSIBLE_ENV := ANSIBLE_LOCAL_TEMP=$(ANSIBLE_LOCAL_TEMP) ANSIBLE_REMOTE_TEMP=$(ANSIBLE_REMOTE_TEMP)
ANSIBLE_SCOPED_RUN = $(RUN_ID_ENV) ANSIBLE_REMOTE_TEMP=$(ANSIBLE_REMOTE_TEMP) $(REPO_ROOT)/scripts/run_with_namespace.sh uv run --with pyyaml python $(REPO_ROOT)/scripts/ansible_scope_runner.py run --inventory $(ANSIBLE_INVENTORY) $(if $(strip $(PLATFORM_TRACE_ID)),--run-id $(PLATFORM_TRACE_ID),)
UPTIME_KUMA_PYTHON ?= $(LOCAL_OVERLAY_ROOT)/uptime-kuma/client-venv/bin/python
UPTIME_KUMA_AUTH_FILE ?= $(LOCAL_OVERLAY_ROOT)/uptime-kuma/admin-session.json
ACTION ?= list-monitors
UPTIME_KUMA_ARGS ?=
PLANE_ARGS ?=
PORTAINER_ARGS ?=
COOLIFY_ARGS ?=
RECEIPT ?=
COMMAND ?=
CONTRACT ?=
SERVICE ?=
DURATION_MINUTES ?= 30
TTL_SECONDS ?= 300
REASON ?=
FORCE ?= false
ALLOW_IN_PLACE_MUTATION ?= false
WARNING_DAYS ?= 45
INACTIVE_DAYS ?= 60
HTTPS_TLS_TIMEOUT_SECONDS ?= 60
FAULT_INJECTION_ARGS ?=
STAGING_RECEIPT ?=
BRANCH ?=
REQUESTER_CLASS ?= human_operator
APPROVER_CLASSES ?= human_operator
DRY_RUN ?= false
ENV ?= production
ENVIRONMENT ?=
service ?=
group ?=
env ?= production
EXTRA_ARGS ?=
AUTOMATION_UV_PYTHON ?= uv run --with pyyaml python
PLATFORM_TRACE_ID ?= $(shell python3 -c 'import uuid; print(uuid.uuid4().hex)')
PLATFORM_INTENT_ID ?=
SURFACE ?=
HOST ?= proxmox_florin
TOOL ?=
IMAGE_ID ?=
IMAGE_TAG ?=
TYPE ?= compose
DEPENDS_ON ?=
OIDC ?= false
HAS_SECRETS ?= true
FQDN ?=
WRITE ?= false
APPLY ?= false
EXCEPTION_REASON ?=
EXCEPTION_JUSTIFICATION ?=
EXCEPTION_OWNER ?=
EXCEPTION_REVIEW_BY ?=
EXCEPTION_EXPIRES_ON ?=
EXCEPTION_CONTROLS_JSON ?=
EXCEPTION_REMEDIATION_PLAN ?=
SECRET_ID ?=
ROTATION_ARGS ?=
COLLECTION_NAMESPACE ?= lv3
COLLECTION_NAME ?= platform
COLLECTION_ROOT := $(REPO_ROOT)/collections/ansible_collections/$(COLLECTION_NAMESPACE)/$(COLLECTION_NAME)
COLLECTION_DIST_DIR ?= $(REPO_ROOT)/build/collections
COLLECTION_VERSION := $(shell ruby -ryaml -e 'puts YAML.load_file(ARGV[0]).fetch("version")' "$(COLLECTION_ROOT)/galaxy.yml")
COLLECTION_TARBALL := $(COLLECTION_DIST_DIR)/$(COLLECTION_NAMESPACE)-$(COLLECTION_NAME)-$(COLLECTION_VERSION).tar.gz
COLLECTION_SERVER ?= internal_galaxy
COLLECTION_INSTALL_PATH ?= $(REPO_ROOT)/build/collection-install
COLLECTION_INSTALL_SOURCE ?= tarball
CHECKS ?=
# Fork operators: override this to point to your own container registry.
# The check-runner images are built by `make build-check-runners`.
CHECK_RUNNER_REGISTRY ?= registry.example.com/check-runner
CHECK_RUNNER_ANSIBLE_TAG ?= 2.17.10
CHECK_RUNNER_PYTHON_TAG ?= 3.12.10
CHECK_RUNNER_INFRA_TAG ?= 2026.03.23
CHECK_RUNNER_SECURITY_TAG ?= 2026.03.23
CHECK_RUNNER_PLATFORM ?= linux/amd64
CHECK_RUNNER_BUILD_NETWORK ?= $(if $(filter docker-build-lv3,$(shell hostname -s 2>/dev/null)),host,)
CHECK_RUNNER_ANSIBLE_IMAGE ?= $(CHECK_RUNNER_REGISTRY)/ansible:$(CHECK_RUNNER_ANSIBLE_TAG)
CHECK_RUNNER_PYTHON_IMAGE ?= $(CHECK_RUNNER_REGISTRY)/python:$(CHECK_RUNNER_PYTHON_TAG)
CHECK_RUNNER_INFRA_IMAGE ?= $(CHECK_RUNNER_REGISTRY)/infra:$(CHECK_RUNNER_INFRA_TAG)
CHECK_RUNNER_SECURITY_IMAGE ?= $(CHECK_RUNNER_REGISTRY)/security:$(CHECK_RUNNER_SECURITY_TAG)
RUN_ID ?= $(PLATFORM_TRACE_ID)
RUN_ID_ENV := LV3_RUN_ID=$(RUN_ID)
ANSIBLE_PLAYBOOK_CMD := $(RUN_ID_ENV) ANSIBLE_REMOTE_TEMP=$(ANSIBLE_REMOTE_TEMP) $(REPO_ROOT)/scripts/run_with_namespace.sh ansible-playbook
TOFU_EXEC_CMD := $(RUN_ID_ENV) $(REPO_ROOT)/scripts/run_with_namespace.sh $(REPO_ROOT)/scripts/tofu_exec.sh
ANSIBLE_TRACE_ARGS := -e platform_trace_id=$(PLATFORM_TRACE_ID) $(if $(PLATFORM_INTENT_ID),-e platform_intent_id=$(PLATFORM_INTENT_ID),)

.PHONY: validate-local push-local prepare-run-namespace validate validate-generated-vars validate-ansible-syntax validate-yaml validate-role-argument-specs validate-ansible-lint validate-ansible-idempotency validate-shell validate-json validate-semgrep validate-compose-runtime-envs validate-dependency-direction validate-data-models validate-cross-catalog validate-types verify-waiver-escalation validate-policy validate-architecture-fitness validate-interface-contracts validate-health-probes validate-alert-rules validate-tofu generate-platform-vars show-platform-facts generate-slo-rules validate-generated-slo generate-https-tls-assurance validate-generated-https-tls-assurance https-tls-assurance generate-status-docs assemble-canonical-truth check-canonical-truth generate-platform-manifest generate-status generate-ops-portal generate-changelog-portal generate-edge-static-sites generate-dependency-diagram generate-diagrams generate-uptime-kuma-monitors validate-generated-uptime-kuma-monitors generate-cross-cutting-artifacts validate-generated-cross-cutting docs deploy-ops-portal
.PHONY: deploy-changelog-portal deploy-docs-portal validate-generated-docs validate-generated-portals receipts receipt-info workflows workflow-info commands command-info interface-contracts interface-contract-info capability-contracts capability-contract-info services show-service environments environment-info preview-create preview-validate preview-destroy preview-list preview-info lanes lane-info execution-lanes execution-lane-info api-publication api-publication-info agent-tools agent-tool-info export-mcp-tools check-image-freshness managed-image-gate sbom-refresh upgrade-container-image pin-image scaffold-service install-hooks pre-push-gate gate-status dr-status atlas-validate atlas-lint atlas-refresh-snapshots atlas-drift-check
.PHONY: backup-coverage-ledger dr-runbook runbook-executor post-merge-gate integration-tests nightly-integration-tests scheduler-watchdog-loop intent-queue-dispatcher platform-observation-loop fault-injection triage-alert triage-calibration search-index-rebuild scan-published-artifacts setup preflight syntax-check syntax-check-monitoring syntax-check-ntfy syntax-check-ntopng syntax-check-falco syntax-check-api-gateway syntax-check-ops-portal syntax-check-dify syntax-check-gitea syntax-check-browser-runner syntax-check-guest-network-policy syntax-check-docker-runtime syntax-check-backup-vm syntax-check-artifact-cache-vm syntax-check-control-plane-recovery syntax-check-uptime-kuma syntax-check-mail-platform syntax-check-mailpit syntax-check-livekit syntax-check-paperless syntax-check-redpanda syntax-check-openbao syntax-check-openfga syntax-check-step-ca syntax-check-temporal syntax-check-headscale syntax-check-semaphore syntax-check-woodpecker syntax-check-windmill syntax-check-restic-config-backup syntax-check-keycloak syntax-check-langfuse syntax-check-glitchtip syntax-check-minio syntax-check-netbox syntax-check-searxng syntax-check-typesense syntax-check-flagsmith syntax-check-crawl4ai
.PHONY: syntax-check-ollama syntax-check-one-api syntax-check-piper syntax-check-n8n syntax-check-open-webui syntax-check-mattermost syntax-check-portainer syntax-check-vaultwarden syntax-check-rag-context syntax-check-secret-rotation syntax-check-dozzle syntax-check-excalidraw syntax-check-realtime collection-sync collection-build collection-publish collection-install check-platform-drift drift-report subdomain-exposure-audit security-posture-report security-headers-audit public-surface-security-scan open-maintenance-window close-maintenance-window ensure-resource-lock-registry resource-locks resource-lock-acquire resource-lock-release resource-lock-heartbeat operator-onboard operator-offboard sync-operators quarterly-access-review install-proxmox configure-network configure-staging-bridge configure-ingress configure-edge-publication configure-tailscale configure-host-control-loops provision-guests
.PHONY: harden-access harden-guest-access harden-security provision-api-access converge-guest-network-policy converge-monitoring converge-ntfy converge-ntopng converge-falco converge-identity-core-watchdog converge-api-gateway converge-ops-portal converge-repo-intake converge-dify converge-gitea converge-browser-runner converge-docker-runtime converge-postgres-vm converge-mail-platform converge-mailpit converge-livekit converge-neko converge-paperless converge-redpanda converge-openbao converge-openfga converge-step-ca converge-temporal converge-headscale converge-semaphore converge-woodpecker converge-windmill converge-restic-config-backup converge-control-plane-recovery converge-keycloak converge-langfuse converge-glitchtip converge-minio converge-netbox converge-searxng converge-typesense converge-crawl4ai converge-ollama converge-one-api converge-piper converge-label-studio converge-n8n converge-open-webui converge-mattermost converge-portainer converge-vaultwarden converge-rag-context converge-dozzle converge-excalidraw converge-realtime converge-flagsmith rotate-secret token-inventory-audit token-exposure-response rotate-keycloak-client-secret
.PHONY: rotate-windmill-token rotate-grafana-service-token rotate-platform-cli-token deploy-uptime-kuma uptime-kuma-manage uptime-robot-manage portainer-manage semaphore-manage woodpecker-manage configure-backups configure-backup-vm configure-artifact-cache-vm database-dns route-dns-assertion-ledger provision-subdomain start-workstream capacity-report weekly-capacity-report disk-space-monitor k6-smoke k6-load k6-soak immutable-guest-replacement-plan synthetic-transaction-replay check-nats-streams apply-nats-streams promote live-apply-group live-apply-service live-apply-site live-apply-waves live-apply-train-status live-apply-train-queue live-apply-train-plan live-apply-train-bundle live-apply-train-run live-apply-train-rollback build-check-runners push-check-runners run-checks warm-cache cache-status fixture-up fixture-down fixture-list fixture-pool-status restic-config-backup restic-config-restore-verify
.PHONY: rotate-windmill-token rotate-grafana-service-token rotate-platform-cli-token deploy-uptime-kuma uptime-kuma-manage uptime-robot-manage portainer-manage semaphore-manage woodpecker-manage configure-backups configure-backup-vm configure-artifact-cache-vm database-dns route-dns-assertion-ledger provision-subdomain start-workstream capacity-report weekly-capacity-report disk-space-monitor k6-smoke k6-load k6-soak immutable-guest-replacement-plan synthetic-transaction-replay check-nats-streams apply-nats-streams promote live-apply-group live-apply-service live-apply-site live-apply-waves live-apply-train-status live-apply-train-queue live-apply-train-plan live-apply-train-bundle live-apply-train-run live-apply-train-rollback build-check-runners push-check-runners run-checks warm-cache cache-status fixture-up fixture-down fixture-list fixture-pool-status restic-config-backup restic-config-restore-verify
.PHONY: validate-certificates fixture-pool-reconcile fixture-reaper install-cli update-cli validate-packer remote-packer-validate packer-template-rebuild remote-tofu-plan remote-tofu-apply tofu-drift tofu-import syntax-check-matrix-synapse converge-matrix-synapse syntax-check-nomad converge-nomad remote-lint remote-validate remote-pre-push remote-packer-build remote-image-build remote-exec check-build-server syntax-check-changedetection converge-changedetection syntax-check-gotenberg converge-gotenberg
.PHONY: syntax-check-tika converge-tika syntax-check-directus converge-directus syntax-check-jupyterhub converge-jupyterhub syntax-check-label-studio converge-label-studio syntax-check-superset converge-superset syntax-check-sftpgo converge-sftpgo syntax-check-neko
.PHONY: syntax-check-tesseract-ocr converge-tesseract-ocr
.PHONY: syntax-check-litellm converge-litellm syntax-check-librechat converge-librechat
.PHONY: syntax-check-flagsmith converge-flagsmith
.PHONY: syntax-check-lago converge-lago
.PHONY: syntax-check-matrix-synapse converge-matrix-synapse
.PHONY: syntax-check-nextcloud converge-nextcloud
.PHONY: syntax-check-nomad converge-nomad
.PHONY: init-local bootstrap bootstrap-minimal verify-bootstrap-proxmox verify-bootstrap-guests verify-platform docker-dev-up docker-dev-up-full docker-dev-down docker-dev-verify docker-dev-converge docker-dev-reset generate-local-example

prepare-run-namespace:
	@$(RUN_ID_ENV) python3 $(REPO_ROOT)/scripts/run_namespace.py --repo-root "$(REPO_ROOT)" --ensure >/dev/null

validate-local:
	@echo "validation gate: running local-only checks (no Docker required)"
	uv run --with pyyaml python scripts/validate_nats_topics.py --validate
	@if [ -f scripts/validate_adr_status_transitions.py ]; then \
		uv run python scripts/validate_adr_status_transitions.py; \
	fi
	@echo "validation gate: local checks passed"

push-local:
	@echo "Pushing with local-only validation (skipping Docker-based remote gates)"
	SKIP_REMOTE_GATE=1 \
	GATE_BYPASS_REASON_CODE=runner_image_pull_failure \
	GATE_BYPASS_DETAIL="Docker registry registry.lv3.org not reachable from local machine" \
	GATE_BYPASS_SUBSTITUTE_EVIDENCE="make validate-local passed; pre-commit hooks passed" \
	GATE_BYPASS_REMEDIATION_REF="docs/adr/0392-convergence-speed-and-incremental-apply.md" \
	GATE_BYPASS_OWNER="$$(git config user.name)" \
	git push origin $$(git rev-parse --abbrev-ref HEAD)

validate:
	$(REPO_ROOT)/scripts/validate_repo.sh

validate-generated-vars:
	$(REPO_ROOT)/scripts/validate_repo.sh generated-vars

validate-ansible-syntax:
	$(REPO_ROOT)/scripts/validate_repo.sh ansible-syntax

validate-yaml:
	$(REPO_ROOT)/scripts/validate_repo.sh yaml

validate-role-argument-specs:
	$(REPO_ROOT)/scripts/validate_repo.sh role-argument-specs

validate-ansible-lint:
	$(REPO_ROOT)/scripts/validate_repo.sh ansible-lint

validate-ansible-idempotency:
	$(REPO_ROOT)/scripts/validate_repo.sh ansible-idempotency

validate-shell:
	$(REPO_ROOT)/scripts/validate_repo.sh shell

validate-json:
	$(REPO_ROOT)/scripts/validate_repo.sh json

validate-semgrep:
	$(REPO_ROOT)/scripts/validate_repo.sh semgrep

validate-compose-runtime-envs:
	$(REPO_ROOT)/scripts/validate_repo.sh compose-runtime-envs

validate-data-models:
	$(REPO_ROOT)/scripts/validate_repo.sh data-models

validate-cross-catalog:
	$(REPO_ROOT)/scripts/validate_repo.sh cross-catalog

verify-waiver-escalation:
	@echo "=== Gate bypass waiver escalation: Z3 formal verification ==="
	uvx --from z3-solver python scripts/verify_waiver_escalation.py
	@echo "=== Z3 proofs passed ==="

validate-types:
	@echo "=== Python type safety validation ==="
	@echo "--- pyright: catalog-integrity and proof scripts + Ansible plugins ---"
	uvx --quiet pyright --pythonversion 3.12 \
		scripts/validate_cross_catalog_integrity.py \
		scripts/verify_waiver_escalation.py \
		scripts/gate_bypass_waivers.py \
		collections/ansible_collections/lv3/platform/plugins/
	@echo "--- bandit: security SAST on catalog-integrity and proof scripts ---"
	uvx --from bandit bandit \
		scripts/validate_cross_catalog_integrity.py \
		scripts/verify_waiver_escalation.py \
		--skip B101,B603,B607 --severity-level medium -q
	@echo "--- crosshair: symbolic contract verification on validation_toolkit ---"
	uvx --from crosshair-tool crosshair check scripts/validation_toolkit.py --per_path_timeout 10 --analysis_kind PEP316
	@echo "=== Python type safety: all checks passed ==="

validate-policy:
	$(REPO_ROOT)/scripts/validate_repo.sh policy

validate-architecture-fitness:
	$(REPO_ROOT)/scripts/validate_repo.sh architecture-fitness

validate-interface-contracts:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/interface_contracts.py --validate

# ADR 0392 Phase 3.1 — Dry-run validation for config-only changes.
# Runs only checks that work without ansible-playbook or Docker.
# When ansible-playbook and uvx are available, add validate-yaml, validate-ansible-syntax,
# validate-interface-contracts to this list.
validate-integration:
	@echo "=== Dry-run integration validation (ADR 0392) ==="
	$(MAKE) validate-json
	@echo "=== Dry-run validation passed — config is syntactically valid ==="

# ADR 0392 Phase 2.2 — Parallel convergence across independent lanes
# Usage: make parallel-converge playbooks="playbooks/services/a.yml playbooks/services/b.yml" env=production max_parallel=4
max_parallel ?= 4
parallel-converge:
	@echo "=== Parallel convergence (ADR 0392 Phase 2.2) ==="
	python3 $(REPO_ROOT)/scripts/ansible_scope_runner.py parallel-run \
		--playbooks $(playbooks) \
		--env $(env) \
		--max-parallel $(max_parallel)

# ADR 0399 — Dummy target for portal-health-sweep Windmill workflow (validator compatibility)
portal-health-sweep:
	@echo "portal-health-sweep is a Windmill workflow, not a Make target"
	exit 0

# ADR 0392 — Timed convergence wrapper (records timing receipts to receipts/convergence-timing/)
# Usage: make time-converge service=api-gateway env=production
# Usage: make time-converge service=api-gateway env=production capture_summary=1
time-converge:
	@echo "=== Timed convergence (ADR 0392) ==="
	python3 $(REPO_ROOT)/scripts/convergence_timer.py run \
		--service $(service) \
		--env $(or $(env),production) \
		$(if $(capture_summary),--capture-summary,)

# ADR 0396 — Generate SLO Prometheus config from catalog with block markers
# Usage: make generate-slo-config
# Usage: make generate-slo-config check=1  (CI mode — exits non-zero if out of date)
generate-slo-config:
	@echo "=== Generating SLO Prometheus config (ADR 0396) ==="
	python3 $(REPO_ROOT)/scripts/generate_slo_config.py $(if $(check),--check,--write)

install-hooks:
	mkdir -p "$$(git rev-parse --git-path hooks)"
	install -m 0755 $(REPO_ROOT)/.githooks/pre-push "$$(git rev-parse --git-path hooks)/pre-push"
	uvx --from pre-commit pre-commit install --install-hooks --hook-type pre-commit

pre-push-gate:
	$(REPO_ROOT)/scripts/remote_exec.sh pre-push-gate --local-fallback

gate-status:
	python3 $(REPO_ROOT)/scripts/gate_status.py | tee /tmp/gate-status-out.txt; \
	if [ -n "$$OUTLINE_API_TOKEN" ]; then \
	  DATE=$$(date -u +%Y-%m-%d); \
	  { printf '# Gate Status: %s\n\n```\n' "$$DATE"; cat /tmp/gate-status-out.txt; printf '```\n'; } | \
	  python3 $(REPO_ROOT)/scripts/outline_tool.py document.publish \
	    --collection "Automation Runs" --title "gate-status-$$DATE" --stdin || true; \
	fi

dr-status:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/generate_dr_report.py

atlas-validate:
	$(REPO_ROOT)/scripts/run_python_with_packages.sh pyyaml -- scripts/atlas_schema.py validate --repo-root $(REPO_ROOT)

atlas-lint:
	$(REPO_ROOT)/scripts/run_python_with_packages.sh docker pyyaml -- scripts/atlas_schema.py lint --repo-root $(REPO_ROOT)

atlas-refresh-snapshots:
	$(REPO_ROOT)/scripts/run_python_with_packages.sh docker pyyaml -- scripts/atlas_schema.py snapshot --repo-root $(REPO_ROOT) --write

atlas-drift-check:
	$(REPO_ROOT)/scripts/run_python_with_packages.sh docker nats-py pyyaml -- scripts/atlas_schema.py drift --repo-root $(REPO_ROOT) --write-receipts --publish-nats --publish-ntfy

backup-coverage-ledger:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/backup_coverage_ledger.py --write-receipt

restic-config-backup:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/trigger_restic_live_apply.py --env $(env) --mode backup --triggered-by manual-backup

restic-config-restore-verify:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/trigger_restic_live_apply.py --env $(env) --mode restore-verify --triggered-by manual-restore-verify

dr-runbook:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/disaster_recovery_runbook.py

runbook-executor:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/runbook_executor.py $(RUNBOOK_EXECUTOR_ARGS)

post-merge-gate:
	$(MAKE) preflight WORKFLOW=post-merge-gate
	python3 $(REPO_ROOT)/config/windmill/scripts/post-merge-gate.py --repo-path $(REPO_ROOT)

stage-smoke-suites:
	python3 $(REPO_ROOT)/scripts/stage_smoke_suites.py $(STAGE_SMOKE_ARGS)

integration-tests:
	uv run --with-requirements $(REPO_ROOT)/requirements/integration-tests.txt python $(REPO_ROOT)/scripts/integration_suite.py

nightly-integration-tests:
	python3 $(REPO_ROOT)/config/windmill/scripts/nightly-integration-tests.py --repo-path $(REPO_ROOT)

scheduler-watchdog-loop:
	uv run --with pyyaml python $(REPO_ROOT)/windmill/scheduler/watchdog-loop.py --repo-path $(REPO_ROOT)

intent-queue-dispatcher:
	python3 $(REPO_ROOT)/scripts/intent_queue_dispatcher.py --repo-root $(REPO_ROOT)

platform-observation-loop:
	python3 $(REPO_ROOT)/config/windmill/scripts/platform-observation-loop.py --repo-path $(REPO_ROOT)

search-index-rebuild:
	python3 $(REPO_ROOT)/config/windmill/scripts/rebuild-search-index.py --repo-path $(REPO_ROOT)
	uv run --with tomli python $(REPO_ROOT)/scripts/published_artifact_secret_scan.py --repo-root $(REPO_ROOT) --path build/search-index

fault-injection:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/lv3_cli.py run fault-injection --approve-risk $(if $(FAULT_INJECTION_ARGS),--args $(FAULT_INJECTION_ARGS),)

network-impairment-matrix:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/lv3_cli.py run network-impairment-matrix $(if $(NETWORK_IMPAIRMENT_MATRIX_ARGS),--args $(NETWORK_IMPAIRMENT_MATRIX_ARGS),)

triage-alert:
	python3 $(REPO_ROOT)/scripts/incident_triage.py $(TRIAGE_ARGS)

triage-calibration:
	python3 $(REPO_ROOT)/config/windmill/scripts/calibrate-triage-rules.py --repo-path $(REPO_ROOT)

setup: install-hooks

build-check-runners:
	docker build --pull --platform $(CHECK_RUNNER_PLATFORM) $(if $(CHECK_RUNNER_BUILD_NETWORK),--network $(CHECK_RUNNER_BUILD_NETWORK)) --tag $(CHECK_RUNNER_ANSIBLE_IMAGE) $(REPO_ROOT)/docker/check-runners/ansible
	docker build --pull --platform $(CHECK_RUNNER_PLATFORM) $(if $(CHECK_RUNNER_BUILD_NETWORK),--network $(CHECK_RUNNER_BUILD_NETWORK)) --tag $(CHECK_RUNNER_PYTHON_IMAGE) $(REPO_ROOT)/docker/check-runners/python
	docker build --pull --platform $(CHECK_RUNNER_PLATFORM) $(if $(CHECK_RUNNER_BUILD_NETWORK),--network $(CHECK_RUNNER_BUILD_NETWORK)) --tag $(CHECK_RUNNER_INFRA_IMAGE) $(REPO_ROOT)/docker/check-runners/infra
	docker build --pull --platform $(CHECK_RUNNER_PLATFORM) $(if $(CHECK_RUNNER_BUILD_NETWORK),--network $(CHECK_RUNNER_BUILD_NETWORK)) --tag $(CHECK_RUNNER_SECURITY_IMAGE) $(REPO_ROOT)/docker/check-runners/security

push-check-runners:
	docker push $(CHECK_RUNNER_ANSIBLE_IMAGE)
	docker push $(CHECK_RUNNER_PYTHON_IMAGE)
	docker push $(CHECK_RUNNER_INFRA_IMAGE)
	docker push $(CHECK_RUNNER_SECURITY_IMAGE)

run-checks:
	python3 $(REPO_ROOT)/scripts/parallel_check.py $(if $(CHECKS),$(CHECKS),--all)

warm-cache:
	python3 $(REPO_ROOT)/config/windmill/scripts/warm-build-cache.py

cache-status:
	python3 $(REPO_ROOT)/scripts/cache_status.py --manifest $(REPO_ROOT)/config/build-cache-manifest.json

subdomain-exposure-audit:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --check-registry --include-live-dns --include-http-auth --include-private-routes --include-tls --include-hetzner-zone --write-receipt --print-report-json

## Ephemeral fixtures (ADR 0088)
fixture-up:
	python3 $(REPO_ROOT)/scripts/fixture_manager.py create $(if $(FIXTURE),"$(FIXTURE)") $(if $(PURPOSE),--purpose "$(PURPOSE)") $(if $(OWNER),--owner "$(OWNER)") $(if $(LIFETIME_HOURS),--lifetime-hours "$(LIFETIME_HOURS)") $(if $(LEASE_PURPOSE),--lease-purpose "$(LEASE_PURPOSE)") $(if $(EPHEMERAL_POLICY),--policy "$(EPHEMERAL_POLICY)") $(if $(ALLOW_EXTEND),--extend)

fixture-down:
	python3 $(REPO_ROOT)/scripts/fixture_manager.py destroy $(if $(FIXTURE),"$(FIXTURE)") $(if $(RECEIPT_ID),--receipt-id "$(RECEIPT_ID)") $(if $(VMID),--vmid "$(VMID)")

fixture-list:
	python3 $(REPO_ROOT)/scripts/fixture_manager.py list $(if $(NO_REFRESH_HEALTH),--no-refresh-health)

fixture-pool-status:
	python3 $(REPO_ROOT)/scripts/fixture_manager.py pool-status --json

fixture-pool-reconcile:
	python3 $(REPO_ROOT)/scripts/fixture_manager.py reconcile-pools $(if $(POOL),--pool "$(POOL)") --json

fixture-reaper:
	python3 $(REPO_ROOT)/config/windmill/scripts/ephemeral-vm-reaper.py

## Backup restore verification (ADR 0099)
restore-verification:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/restore_verification.py $(RESTORE_ARGS)

## Synthetic transaction replay (ADR 0190)
synthetic-transaction-replay:
	python3 $(REPO_ROOT)/scripts/synthetic_transaction_replay.py $(SYNTHETIC_REPLAY_ARGS)

## Seed snapshots (ADR 0187)
seed-snapshot-build:
	@test -n "$(SEED_CLASS)" || (echo "set SEED_CLASS=<tiny|standard|recovery>"; exit 1)
	uv run --with pyyaml python $(REPO_ROOT)/scripts/seed_data_snapshots.py build --seed-class "$(SEED_CLASS)"

seed-snapshot-list:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/seed_data_snapshots.py list $(if $(SEED_CLASS),--seed-class "$(SEED_CLASS)")

seed-snapshot-verify:
	@test -n "$(SEED_CLASS)" || (echo "set SEED_CLASS=<tiny|standard|recovery>"; exit 1)
	uv run --with pyyaml python $(REPO_ROOT)/scripts/seed_data_snapshots.py verify --seed-class "$(SEED_CLASS)" $(if $(SNAPSHOT_ID),--snapshot-id "$(SNAPSHOT_ID)")

seed-snapshot-publish:
	@test -n "$(SEED_CLASS)" || (echo "set SEED_CLASS=<tiny|standard|recovery>"; exit 1)
	uv run --with pyyaml python $(REPO_ROOT)/scripts/seed_data_snapshots.py publish --seed-class "$(SEED_CLASS)" $(if $(SNAPSHOT_ID),--snapshot-id "$(SNAPSHOT_ID)")

## Platform CLI (ADR 0090)
install-cli:
	@if command -v pipx >/dev/null 2>&1; then \
		pipx install --editable $(REPO_ROOT) --force; \
	else \
		python3 -m pip install --user --editable $(REPO_ROOT); \
	fi

update-cli: install-cli

generate-platform-vars:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/generate_platform_vars.py --write

generate-slo-rules:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/generate_slo_rules.py --write

validate-generated-slo:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/generate_slo_rules.py --check

generate-https-tls-assurance:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/generate_https_tls_assurance.py --write

validate-generated-https-tls-assurance:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/generate_https_tls_assurance.py --check

generate-uptime-kuma-monitors:
	python3 $(REPO_ROOT)/scripts/uptime_contract.py --write

validate-generated-uptime-kuma-monitors:
	python3 $(REPO_ROOT)/scripts/uptime_contract.py --check

generate-cross-cutting-artifacts:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/generate_cross_cutting_artifacts.py --write --only hairpin

validate-generated-cross-cutting:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/generate_cross_cutting_artifacts.py --check --only hairpin

show-platform-facts:
	uvx --from ansible-core ansible-inventory -i $(ANSIBLE_INVENTORY) --host $(HOST) --yaml

validate-health-probes:
	$(REPO_ROOT)/scripts/validate_repo.sh health-probes

validate-alert-rules:
	$(REPO_ROOT)/scripts/validate_repo.sh alert-rules

syntax-check-realtime:
	ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/realtime.yml --syntax-check

validate-tofu:
	$(TOFU_EXEC_CMD) validate all

collection-sync:
	mkdir -p $(COLLECTION_ROOT)/playbooks
	rsync -a --delete $(REPO_ROOT)/playbooks/ $(COLLECTION_ROOT)/playbooks/

collection-build: collection-sync
	mkdir -p $(COLLECTION_DIST_DIR)
	uvx --from ansible-core ansible-galaxy collection build $(COLLECTION_ROOT) --output-path $(COLLECTION_DIST_DIR) --force

collection-publish: collection-build
	python3 $(REPO_ROOT)/config/windmill/scripts/collection-publish.py --repo-root $(REPO_ROOT) --server $(COLLECTION_SERVER)

collection-install: collection-build
	@if [ "$(COLLECTION_INSTALL_SOURCE)" = "server" ]; then \
		uvx --from ansible-core ansible-galaxy collection install $(COLLECTION_NAMESPACE).$(COLLECTION_NAME):$(COLLECTION_VERSION) --server $(COLLECTION_SERVER) -p $(COLLECTION_INSTALL_PATH) --force; \
	else \
		uvx --from ansible-core ansible-galaxy collection install $(COLLECTION_TARBALL) -p $(COLLECTION_INSTALL_PATH) --force; \
	fi

check-image-freshness:
	$(REPO_ROOT)/scripts/container_image_policy.py --check-freshness

managed-image-gate:
	python3 $(REPO_ROOT)/scripts/managed_image_gate.py $(if $(BASELINE_REVISION),--baseline-revision "$(BASELINE_REVISION)",)

sbom-refresh:
	uv run --with nats-py --with pyyaml python $(REPO_ROOT)/scripts/sbom_refresh.py $(if $(IMAGE_ID),--image-id "$(IMAGE_ID)",) $(if $(filter true,$(PUBLISH_NATS)),--publish-nats,) $(if $(filter true,$(SEND_NTFY_ALERTS)),--send-ntfy-alerts,) $(if $(filter true,$(PRINT_REPORT_JSON)),--print-report-json,)

upgrade-container-image:
	@test -n "$(IMAGE_ID)" || (echo "set IMAGE_ID=<image-id>"; exit 1)
	python3 $(REPO_ROOT)/scripts/upgrade_container_image.py --image-id "$(IMAGE_ID)" $(if $(IMAGE_TAG),--tag "$(IMAGE_TAG)",) $(if $(filter true,$(WRITE)),--write,) $(if $(filter true,$(APPLY)),--apply,) $(if $(filter true,$(SKIP_ARTIFACT_CACHE)),--skip-artifact-cache,) $(if $(EXCEPTION_JUSTIFICATION),--exception-justification "$(EXCEPTION_JUSTIFICATION)",) $(if $(EXCEPTION_REASON),--exception-reason "$(EXCEPTION_REASON)",) $(if $(EXCEPTION_OWNER),--exception-owner "$(EXCEPTION_OWNER)",) $(if $(EXCEPTION_EXPIRES_ON),--exception-expires-on "$(EXCEPTION_EXPIRES_ON)",) $(if $(EXCEPTION_REVIEW_BY),--exception-review-by "$(EXCEPTION_REVIEW_BY)",) $(if $(EXCEPTION_CONTROLS_JSON),--exception-controls-json '$(EXCEPTION_CONTROLS_JSON)',) $(if $(EXCEPTION_REMEDIATION_PLAN),--exception-remediation-plan "$(EXCEPTION_REMEDIATION_PLAN)",)

pin-image:
	@test -n "$(IMAGE)" || (echo "set IMAGE=<registry/repository:tag>"; exit 1)
	python3 $(REPO_ROOT)/scripts/pin_image_ref.py --image "$(IMAGE)"

scaffold-service:
	@test -n "$(NAME)" || (echo "set NAME=<service-name>"; exit 1)
	uvx --from pyyaml python $(REPO_ROOT)/scripts/generate_service_scaffold.py --repo-root $(REPO_ROOT) --name "$(NAME)" --type "$(TYPE)" $(if $(DESCRIPTION),--description "$(DESCRIPTION)",) $(if $(CATEGORY),--category "$(CATEGORY)",) $(if $(VM),--vm "$(VM)",) $(if $(VMID),--vmid $(VMID),) $(if $(DEPENDS_ON),--depends-on "$(DEPENDS_ON)",) $(if $(PORT),--port $(PORT),) $(if $(SUBDOMAIN),--subdomain "$(SUBDOMAIN)",) $(if $(EXPOSURE),--exposure "$(EXPOSURE)",) --$(if $(filter true,$(OIDC)),,no-)oidc --$(if $(filter true,$(HAS_SECRETS)),,no-)has-secrets $(if $(IMAGE),--image "$(IMAGE)",)

generate-status-docs:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/generate_release_notes.py --write-root-summaries
	uvx --from pyyaml python $(REPO_ROOT)/scripts/generate_status_docs.py --write

generate-diagrams:
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/generate_diagrams.py --write

assemble-canonical-truth:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/canonical_truth.py --write

check-canonical-truth:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/canonical_truth.py --check

generate-platform-manifest:
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/platform_manifest.py --write

generate-ops-portal:
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/generate_ops_portal.py --write

generate-changelog-portal:
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/generate_changelog_portal.py --write
	uv run --with tomli python $(REPO_ROOT)/scripts/published_artifact_secret_scan.py --repo-root $(REPO_ROOT) --path build/changelog-portal

generate-edge-static-sites: generate-changelog-portal docs

scan-published-artifacts:
	uv run --with tomli python $(REPO_ROOT)/scripts/published_artifact_secret_scan.py --repo-root $(REPO_ROOT)

docs:
	uv run --with-requirements $(REPO_ROOT)/requirements/docs.txt python $(REPO_ROOT)/scripts/build_docs_portal.py

deploy-ops-portal: generate-ops-portal generate-edge-static-sites
	$(MAKE) configure-edge-publication

deploy-changelog-portal: generate-edge-static-sites
	$(MAKE) configure-edge-publication

deploy-docs-portal: generate-edge-static-sites
	$(MAKE) configure-edge-publication

generate-status: generate-slo-rules generate-status-docs generate-platform-manifest generate-ops-portal generate-changelog-portal generate-diagrams docs

validate-generated-docs:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/generate_release_notes.py --check-root-summaries
	uvx --from pyyaml python $(REPO_ROOT)/scripts/generate_status_docs.py --check
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/generate_diagrams.py --check

validate-generated-portals:
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/generate_ops_portal.py --check
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/generate_changelog_portal.py --check
	uv run --with pyyaml python $(REPO_ROOT)/scripts/generate_slo_rules.py --check
	$(MAKE) docs

reconcile-portals: ## Regenerate all portal artifacts from canonical catalogs
	python3 -m scripts.reconciliation.cli reconcile-all

check-portal-drift: ## Check if any portal artifacts are stale
	python3 -m scripts.reconciliation.cli check-drift

receipts:
	$(REPO_ROOT)/scripts/live_apply_receipts.py --list

receipt-info:
	@test -n "$(RECEIPT)" || (echo "set RECEIPT=<receipt-id>"; exit 1)
	$(REPO_ROOT)/scripts/live_apply_receipts.py --receipt $(RECEIPT)

workflows:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/workflow_catalog.py --list

workflow-info:
	@test -n "$(WORKFLOW)" || (echo "set WORKFLOW=<workflow-id>"; exit 1)
	uvx --from pyyaml python $(REPO_ROOT)/scripts/workflow_catalog.py --workflow $(WORKFLOW)

commands:
	$(REPO_ROOT)/scripts/command_catalog.py --list

command-info:
	@test -n "$(COMMAND)" || (echo "set COMMAND=<command-id>"; exit 1)
	$(REPO_ROOT)/scripts/command_catalog.py --command $(COMMAND)

interface-contracts:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/interface_contracts.py --list

interface-contract-info:
	@test -n "$(CONTRACT)" || (echo "set CONTRACT=<contract-id>"; exit 1)
	uvx --from pyyaml python $(REPO_ROOT)/scripts/interface_contracts.py --contract $(CONTRACT)

services:
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/service_catalog.py --list

show-service:
	@test -n "$(SERVICE)" || (echo "set SERVICE=<service-id>"; exit 1)
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/service_catalog.py --service $(SERVICE)

environments:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/environment_topology.py --list

environment-info:
	@test -n "$(ENVIRONMENT)" || (echo "set ENVIRONMENT=<production|staging>"; exit 1)
	uvx --from pyyaml python $(REPO_ROOT)/scripts/environment_topology.py --environment $(ENVIRONMENT)

preview-create: generate-platform-manifest
	@test -n "$(WORKSTREAM)" || (echo "set WORKSTREAM=<workstream-id>"; exit 1)
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/preview_environment.py create --workstream "$(WORKSTREAM)" $(if $(BRANCH),--branch "$(BRANCH)",) $(if $(PROFILE),--profile "$(PROFILE)",) $(if $(MANIFEST),--manifest "$(MANIFEST)",) $(if $(OWNER),--owner "$(OWNER)",) $(if $(TTL_HOURS),--ttl-hours "$(TTL_HOURS)",) $(if $(POLICY),--policy "$(POLICY)",) $(if $(filter true,$(JSON)),--json,)

preview-validate:
	@test -n "$(PREVIEW_ID)" || (echo "set PREVIEW_ID=<preview-id>"; exit 1)
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/preview_environment.py validate --preview-id "$(PREVIEW_ID)" $(if $(filter true,$(JSON)),--json,)

preview-destroy:
	@test -n "$(PREVIEW_ID)" || (echo "set PREVIEW_ID=<preview-id>"; exit 1)
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/preview_environment.py destroy --preview-id "$(PREVIEW_ID)" $(if $(filter true,$(JSON)),--json,)

preview-list:
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/preview_environment.py list $(if $(filter true,$(JSON)),--json,)

preview-info:
	@test -n "$(PREVIEW_ID)" || (echo "set PREVIEW_ID=<preview-id>"; exit 1)
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/preview_environment.py show --preview-id "$(PREVIEW_ID)" $(if $(filter true,$(ARCHIVED)),--archived,) $(if $(filter true,$(JSON)),--json,)

lanes:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/control_plane_lanes.py --list

lane-info:
	@test -n "$(LANE)" || (echo "set LANE=<command|api|message|event>"; exit 1)
	uvx --from pyyaml python $(REPO_ROOT)/scripts/control_plane_lanes.py --lane $(LANE)

execution-lanes:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/execution_lanes.py --list

execution-lane-info:
	@test -n "$(LANE)" || (echo "set LANE=<lane-id>"; exit 1)
	uvx --from pyyaml python $(REPO_ROOT)/scripts/execution_lanes.py --lane $(LANE)

api-publication:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/api_publication.py --list

api-publication-info:
	@test -n "$(SURFACE)" || (echo "set SURFACE=<surface-id>"; exit 1)
	uvx --from pyyaml python $(REPO_ROOT)/scripts/api_publication.py --surface $(SURFACE)

agent-tools:
	@$(REPO_ROOT)/scripts/agent_tool_registry.py --list

agent-tool-info:
	@test -n "$(TOOL)" || (echo "set TOOL=<tool-name>"; exit 1)
	@$(REPO_ROOT)/scripts/agent_tool_registry.py --tool $(TOOL)

export-mcp-tools:
	@$(REPO_ROOT)/scripts/agent_tool_registry.py --export-mcp

preflight:
	@if [ -z "$(WORKFLOW)" ]; then \
		uv run --with pyyaml python $(REPO_ROOT)/scripts/preflight_controller_local.py --list; \
		echo "set WORKFLOW=<workflow-id>"; \
		exit 0; \
	else \
		uv run --with pyyaml python $(REPO_ROOT)/scripts/preflight_controller_local.py --workflow $(WORKFLOW); \
	fi

syntax-check:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --syntax-check

syntax-check-monitoring:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/monitoring-stack.yml --syntax-check

syntax-check-ntfy:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/ntfy.yml --syntax-check

syntax-check-ntopng:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/ntopng.yml --syntax-check

syntax-check-falco:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/falco.yml --syntax-check

syntax-check-guest-network-policy:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/guest-network-policy.yml --syntax-check

syntax-check-docker-runtime:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/docker-runtime.yml --syntax-check

syntax-check-docker-publication-assurance:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/docker-publication-assurance.yml --syntax-check

syntax-check-backup-vm:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/backup-vm.yml --syntax-check

syntax-check-artifact-cache-vm:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/artifact-cache-vm.yml --syntax-check

syntax-check-control-plane-recovery:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/control-plane-recovery.yml --syntax-check

syntax-check-uptime-kuma:
	ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/uptime-kuma.yml --syntax-check

syntax-check-mail-platform:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/mail-platform.yml --syntax-check

syntax-check-openbao:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/openbao.yml --syntax-check

syntax-check-openfga:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/openfga.yml --syntax-check

syntax-check-step-ca:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/step-ca.yml --syntax-check

syntax-check-temporal:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/temporal.yml --syntax-check

syntax-check-tika:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/tika.yml --syntax-check

syntax-check-tesseract-ocr:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/tesseract-ocr.yml --syntax-check

syntax-check-directus:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/directus.yml --syntax-check

syntax-check-jupyterhub:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/jupyterhub.yml --syntax-check

syntax-check-label-studio:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/label-studio.yml --syntax-check

syntax-check-superset:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/superset.yml --syntax-check

syntax-check-sftpgo:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/sftpgo.yml --syntax-check

syntax-check-semaphore:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/semaphore.yml --syntax-check

syntax-check-woodpecker:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/woodpecker.yml --syntax-check

syntax-check-headscale:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/headscale.yml --syntax-check

syntax-check-windmill:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/windmill.yml --syntax-check

syntax-check-restic-config-backup:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/restic-config-backup.yml --syntax-check

syntax-check-coolify:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/coolify.yml --syntax-check

syntax-check-keycloak:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/keycloak.yml --syntax-check

syntax-check-harbor:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/harbor.yml --syntax-check

syntax-check-langfuse:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/langfuse.yml --syntax-check

syntax-check-minio:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/minio.yml --syntax-check

syntax-check-flagsmith:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/flagsmith.yml --syntax-check

syntax-check-lago:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/lago.yml --syntax-check

syntax-check-plausible:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/plausible.yml --syntax-check

syntax-check-glitchtip:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/glitchtip.yml --syntax-check

syntax-check-plane:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/plane.yml --syntax-check

syntax-check-api-gateway:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/api-gateway.yml --syntax-check

syntax-check-ops-portal:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/ops-portal.yml --syntax-check

syntax-check-dify:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/dify.yml --syntax-check

syntax-check-gitea:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/gitea.yml --syntax-check

syntax-check-browser-runner:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/browser-runner.yml --syntax-check

syntax-check-mailpit:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/mailpit.yml --syntax-check

syntax-check-livekit:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/livekit.yml --syntax-check

syntax-check-neko:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/neko.yml --syntax-check

syntax-check-paperless:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/paperless.yml --syntax-check

syntax-check-redpanda:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/redpanda.yml --syntax-check
syntax-check-changedetection:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/changedetection.yml --syntax-check

syntax-check-crawl4ai:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/crawl4ai.yml --syntax-check

syntax-check-gotenberg:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/gotenberg.yml --syntax-check

syntax-check-typesense:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/typesense.yml --syntax-check

syntax-check-netbox:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/netbox.yml --syntax-check

syntax-check-searxng:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/searxng.yml --syntax-check

syntax-check-ollama:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/ollama.yml --syntax-check

syntax-check-one-api:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/one-api.yml --syntax-check

syntax-check-piper:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/piper.yml --syntax-check

syntax-check-matrix-synapse:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/matrix-synapse.yml --syntax-check

syntax-check-n8n:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/n8n.yml --syntax-check

syntax-check-nextcloud:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/nextcloud.yml --syntax-check

syntax-check-nomad:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/nomad.yml --syntax-check

syntax-check-dozzle:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/dozzle.yml --syntax-check

syntax-check-open-webui:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/open-webui.yml --syntax-check

syntax-check-serverclaw:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/serverclaw.yml --syntax-check

syntax-check-homepage:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/homepage.yml --syntax-check

syntax-check-excalidraw:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/excalidraw.yml --syntax-check

syntax-check-portainer:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/portainer.yml --syntax-check

syntax-check-vaultwarden:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/vaultwarden.yml --syntax-check

syntax-check-rag-context:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/rag-context.yml --syntax-check

syntax-check-mattermost:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/mattermost.yml --syntax-check

syntax-check-secret-rotation:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/secret-rotation.yml --syntax-check

check-platform-drift:
	uv run --with pyyaml --with nats-py python $(REPO_ROOT)/scripts/platform_observation_tool.py

drift-report:
	@test -n "$(ENV)" || (echo "set ENV=<production|staging>"; exit 1)
	uv run --with pyyaml --with dnspython --with nats-py python $(REPO_ROOT)/scripts/drift_detector.py --env "$(ENV)"

security-posture-report:
	@test -n "$(ENV)" || (echo "set ENV=<production|staging>"; exit 1)
	uv run --with ansible-core --with pyyaml --with nats-py python $(REPO_ROOT)/scripts/security_posture_report.py --env "$(ENV)"

public-surface-security-scan:
	@test -n "$(ENV)" || (echo "set ENV=<production|staging>"; exit 1)
	uv run --with pyyaml --with nats-py python $(REPO_ROOT)/scripts/public_surface_scan.py --env "$(ENV)"

https-tls-assurance:
	@test -n "$(ENV)" || (echo "set ENV=<production|staging>"; exit 1)
	uv run --with pyyaml python $(REPO_ROOT)/scripts/https_tls_assurance.py --env "$(ENV)" --timeout-seconds "$(HTTPS_TLS_TIMEOUT_SECONDS)"

security-headers-audit:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/security_headers_audit.py

open-maintenance-window:
	$(MAKE) preflight WORKFLOW=open-maintenance-window
	@test -n "$(SERVICE)" || (echo "set SERVICE=<service-id>"; exit 1)
	@test -n "$(REASON)" || (echo "set REASON=<planned-change-reason>"; exit 1)
	uv run --with pyyaml --with nats-py python $(REPO_ROOT)/scripts/maintenance_window_tool.py open --service "$(SERVICE)" --reason "$(REASON)" --duration-minutes $(DURATION_MINUTES)

close-maintenance-window:
	$(MAKE) preflight WORKFLOW=close-maintenance-window
	@test -n "$(SERVICE)" || (echo "set SERVICE=<service-id|all>"; exit 1)
	uv run --with pyyaml --with nats-py python $(REPO_ROOT)/scripts/maintenance_window_tool.py close --service "$(SERVICE)" $(if $(filter true,$(FORCE)),--force,)

ensure-resource-lock-registry:
	python3 $(REPO_ROOT)/scripts/resource_lock_tool.py ensure-state

resource-locks:
	python3 $(REPO_ROOT)/scripts/resource_lock_tool.py list

resource-lock-acquire:
	@test -n "$(RESOURCE)" || (echo "set RESOURCE=<resource-path>"; exit 1)
	@test -n "$(HOLDER)" || (echo "set HOLDER=<lock-holder-id>"; exit 1)
	@test -n "$(LOCK_TYPE)" || (echo "set LOCK_TYPE=<shared|intent|exclusive>"; exit 1)
	python3 $(REPO_ROOT)/scripts/resource_lock_tool.py acquire --resource "$(RESOURCE)" --holder "$(HOLDER)" --lock-type "$(LOCK_TYPE)" --ttl-seconds $(TTL_SECONDS) $(if $(WAIT_SECONDS),--wait-seconds $(WAIT_SECONDS),) $(if $(CONTEXT_ID),--context-id "$(CONTEXT_ID)",)

resource-lock-release:
	@test -n "$(RESOURCE)" || (echo "set RESOURCE=<resource-path>"; exit 1)
	@test -n "$(HOLDER)" || (echo "set HOLDER=<lock-holder-id>"; exit 1)
	python3 $(REPO_ROOT)/scripts/resource_lock_tool.py release --resource "$(RESOURCE)" --holder "$(HOLDER)"

resource-lock-heartbeat:
	@test -n "$(LOCK_ID)" || (echo "set LOCK_ID=<lock-id>"; exit 1)
	python3 $(REPO_ROOT)/scripts/resource_lock_tool.py heartbeat --lock-id "$(LOCK_ID)" --ttl-seconds $(TTL_SECONDS)

operator-onboard:
	$(MAKE) preflight WORKFLOW=operator-onboard
	@test -n "$(NAME)" || (echo "set NAME=<operator-name>"; exit 1)
	@test -n "$(EMAIL)" || (echo "set EMAIL=<operator-email>"; exit 1)
	@test -n "$(ROLE)" || (echo "set ROLE=<admin|operator|viewer>"; exit 1)
	@case "$(ROLE)" in admin|operator) test -n "$(SSH_KEY)" || { echo "set SSH_KEY=@/path/to/public-key.pub"; exit 1; } ;; viewer) : ;; *) echo "ROLE must be admin, operator, or viewer"; exit 1 ;; esac
	uvx --from pyyaml python $(REPO_ROOT)/scripts/operator_manager.py onboard --name "$(NAME)" --email "$(EMAIL)" --role "$(ROLE)" $(if $(SSH_KEY),--ssh-key "$(SSH_KEY)",) $(if $(OPERATOR_ID),--id "$(OPERATOR_ID)",) $(if $(KEYCLOAK_USERNAME),--keycloak-username "$(KEYCLOAK_USERNAME)",) $(if $(TAILSCALE_LOGIN_EMAIL),--tailscale-login-email "$(TAILSCALE_LOGIN_EMAIL)",) $(if $(TAILSCALE_DEVICE_NAME),--tailscale-device-name "$(TAILSCALE_DEVICE_NAME)",) $(if $(BOOTSTRAP_PASSWORD),--bootstrap-password "$(BOOTSTRAP_PASSWORD)",) --emit-json

operator-offboard:
	$(MAKE) preflight WORKFLOW=operator-offboard
	@test -n "$(OPERATOR_ID)" || (echo "set OPERATOR_ID=<operator-id>"; exit 1)
	uvx --from pyyaml python $(REPO_ROOT)/scripts/operator_manager.py offboard --id "$(OPERATOR_ID)" $(if $(REASON),--reason "$(REASON)",) --emit-json

sync-operators:
	$(MAKE) preflight WORKFLOW=sync-operators
	uvx --from pyyaml python $(REPO_ROOT)/scripts/operator_manager.py sync $(if $(OPERATOR_ID),--id "$(OPERATOR_ID)",) $(if $(filter true,$(DRY_RUN)),--dry-run,) --emit-json

quarterly-access-review:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/operator_manager.py quarterly-review --warning-days $(WARNING_DAYS) --inactive-days $(INACTIVE_DAYS) $(if $(filter true,$(DRY_RUN)),--dry-run,) --emit-json

install-proxmox:
	$(MAKE) preflight WORKFLOW=install-proxmox
	$(ANSIBLE_PLAYBOOK_CMD) -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY)

configure-network:
	$(MAKE) preflight WORKFLOW=configure-network
	$(ANSIBLE_PLAYBOOK_CMD) -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags repository,network

configure-staging-bridge:
	$(MAKE) preflight WORKFLOW=configure-network
	$(ANSIBLE_PLAYBOOK_CMD) -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/proxmox-staging-bridge.yml --private-key $(BOOTSTRAP_KEY)

configure-ingress:
	$(MAKE) preflight WORKFLOW=configure-ingress
	$(ANSIBLE_PLAYBOOK_CMD) -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags ingress

validate-certificates:
	uv run python3 $(REPO_ROOT)/scripts/certificate_validator.py --check-all

configure-edge-publication:
	$(MAKE) preflight WORKFLOW=configure-edge-publication
	$(MAKE) generate-platform-vars
	uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --write-registry --validate
	$(MAKE) generate-changelog-portal docs
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/public-edge.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump $(EXTRA_ARGS)
	$(MAKE) validate-certificates

configure-tailscale:
	$(MAKE) preflight WORKFLOW=configure-tailscale
	$(ANSIBLE_PLAYBOOK_CMD) -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags tailscale

configure-host-control-loops:
	$(MAKE) preflight WORKFLOW=configure-host-control-loops
	$(ANSIBLE_PLAYBOOK_CMD) -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/proxmox-install.yml --private-key $(BOOTSTRAP_KEY) --tags control-loops

provision-guests:
	$(MAKE) preflight WORKFLOW=provision-guests
	$(ANSIBLE_PLAYBOOK_CMD) -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags guests

harden-access:
	$(MAKE) preflight WORKFLOW=harden-access
	$(ANSIBLE_PLAYBOOK_CMD) -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags access

harden-guest-access:
	$(MAKE) preflight WORKFLOW=harden-guest-access
	$(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/guest-access.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY)

harden-security:
	$(MAKE) preflight WORKFLOW=harden-security
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} $(ANSIBLE_PLAYBOOK_CMD) -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags security

provision-api-access:
	$(MAKE) preflight WORKFLOW=provision-api-access
	$(ANSIBLE_PLAYBOOK_CMD) -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags api-access

converge-guest-network-policy:
	$(MAKE) preflight WORKFLOW=converge-guest-network-policy
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/guest-network-policy.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-monitoring:
	$(MAKE) preflight WORKFLOW=converge-monitoring
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/monitoring-stack.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-ntfy:
	$(MAKE) preflight WORKFLOW=converge-ntfy
	uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate
	$(MAKE) generate-edge-static-sites
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/ntfy.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/ntfy.yml $(ANSIBLE_TRACE_ARGS) $(EXTRA_ARGS)

converge-ntopng:
	$(MAKE) preflight WORKFLOW=converge-ntopng
	$(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/ntopng.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY)

converge-falco:
	$(MAKE) preflight WORKFLOW=converge-falco
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/falco.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-docker-runtime:
	$(MAKE) preflight WORKFLOW=converge-docker-runtime
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/docker-runtime.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-docker-publication-assurance:
	$(MAKE) preflight WORKFLOW=converge-docker-publication-assurance
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/docker-publication-assurance.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-postgres-vm:
	$(MAKE) preflight WORKFLOW=converge-postgres-vm
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/postgres-vm.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-mail-platform:
	$(MAKE) preflight WORKFLOW=converge-mail-platform
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/mail-platform.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-openbao:
	$(MAKE) preflight WORKFLOW=converge-openbao
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/openbao.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-openfga:
	$(MAKE) preflight WORKFLOW=converge-openfga
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/openfga.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-step-ca:
	$(MAKE) preflight WORKFLOW=converge-step-ca
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/step-ca.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-temporal:
	$(MAKE) preflight WORKFLOW=converge-temporal
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/temporal.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-tika:
	$(MAKE) preflight WORKFLOW=converge-tika
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/tika.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump $(ANSIBLE_TRACE_ARGS)

converge-tesseract-ocr:
	$(MAKE) preflight WORKFLOW=converge-tesseract-ocr
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/tesseract-ocr.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump $(ANSIBLE_TRACE_ARGS)

converge-directus:
	$(MAKE) preflight WORKFLOW=converge-directus
	uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate
	$(MAKE) generate-edge-static-sites
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/directus.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/directus.yml $(ANSIBLE_TRACE_ARGS)

converge-jupyterhub:
	$(MAKE) preflight WORKFLOW=converge-jupyterhub
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/jupyterhub.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/jupyterhub.yml $(ANSIBLE_TRACE_ARGS)

converge-label-studio:
	$(MAKE) preflight WORKFLOW=converge-label-studio
	uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate
	$(MAKE) generate-edge-static-sites
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/label-studio.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/label-studio.yml $(ANSIBLE_TRACE_ARGS)

converge-superset:
	$(MAKE) preflight WORKFLOW=converge-superset
	uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate
	$(MAKE) generate-edge-static-sites
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/superset.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/superset.yml $(ANSIBLE_TRACE_ARGS)

converge-sftpgo:
	$(MAKE) preflight WORKFLOW=converge-sftpgo
	uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate
	$(MAKE) generate-edge-static-sites
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/sftpgo.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/sftpgo.yml $(ANSIBLE_TRACE_ARGS)

converge-semaphore:
	$(MAKE) preflight WORKFLOW=converge-semaphore
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/semaphore.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-woodpecker:
	$(MAKE) preflight WORKFLOW=converge-woodpecker
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/woodpecker.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-headscale:
	$(MAKE) preflight WORKFLOW=converge-headscale
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/headscale.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/headscale.yml

converge-windmill:
	$(MAKE) preflight WORKFLOW=converge-windmill
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/windmill.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e windmill_worker_checkout_repo_root_local_dir=$(REPO_ROOT) $(EXTRA_ARGS)

converge-restic-config-backup:
	$(MAKE) preflight WORKFLOW=converge-restic-config-backup
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/restic-config-backup.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump $(ANSIBLE_TRACE_ARGS) $(EXTRA_ARGS)

converge-coolify:
	$(MAKE) preflight WORKFLOW=converge-coolify
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/coolify.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-identity-core-watchdog:
	$(MAKE) preflight WORKFLOW=converge-identity-core-watchdog
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/identity-core-watchdog.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-keycloak:
	$(MAKE) preflight WORKFLOW=converge-keycloak
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/keycloak.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-harbor:
	$(MAKE) preflight WORKFLOW=converge-harbor
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/harbor.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-langfuse:
	$(MAKE) preflight WORKFLOW=converge-langfuse
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/langfuse.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/langfuse.yml

converge-minio:
	$(MAKE) preflight WORKFLOW=converge-minio
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/minio.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/minio.yml

converge-flagsmith:
	$(MAKE) preflight WORKFLOW=converge-flagsmith
	uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate
	$(MAKE) generate-edge-static-sites
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/flagsmith.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/flagsmith.yml $(ANSIBLE_TRACE_ARGS)

converge-lago:
	$(MAKE) preflight WORKFLOW=converge-lago
	uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate
	$(MAKE) generate-edge-static-sites
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/lago.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/lago.yml $(ANSIBLE_TRACE_ARGS)

converge-plausible:
	$(MAKE) preflight WORKFLOW=converge-plausible
	uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate
	$(MAKE) generate-edge-static-sites
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/plausible.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/plausible.yml

converge-glitchtip:
	$(MAKE) preflight WORKFLOW=converge-glitchtip
	uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate
	$(MAKE) generate-edge-static-sites
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/glitchtip.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/glitchtip.yml $(ANSIBLE_TRACE_ARGS) $(EXTRA_ARGS)

converge-plane:
	$(MAKE) preflight WORKFLOW=converge-plane
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/plane.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-api-gateway:
	$(MAKE) preflight WORKFLOW=converge-api-gateway
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/api-gateway.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e api_gateway_repo_root=$(REPO_ROOT) $(ANSIBLE_TRACE_ARGS)

converge-ops-portal:
	$(MAKE) preflight WORKFLOW=converge-ops-portal
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/ops-portal.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e ops_portal_repo_root=$(REPO_ROOT) $(ANSIBLE_TRACE_ARGS)

converge-repo-intake:
	$(MAKE) preflight WORKFLOW=converge-repo-intake
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/repo-intake.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump $(ANSIBLE_TRACE_ARGS)

converge-dify:
	$(MAKE) preflight WORKFLOW=converge-dify
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/dify.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/dify.yml

converge-browser-runner:
	$(MAKE) preflight WORKFLOW=converge-browser-runner
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/browser-runner.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump $(ANSIBLE_TRACE_ARGS)

converge-mailpit:
	$(MAKE) preflight WORKFLOW=converge-mailpit
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/mailpit.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-livekit:
	$(MAKE) preflight WORKFLOW=converge-livekit
	uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate
	$(MAKE) generate-edge-static-sites
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/livekit.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/livekit.yml $(ANSIBLE_TRACE_ARGS) $(EXTRA_ARGS)

converge-neko:
	$(MAKE) preflight WORKFLOW=converge-neko
	$(MAKE) generate-edge-static-sites
	@echo "Syncing neko_instances from Keycloak (--dry-run to preview)..."
	python3 $(REPO_ROOT)/scripts/neko_tool.py sync-from-keycloak \
	  --keycloak-url http://10.10.10.20:8091 \
	  --group /lv3-platform-admins
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/neko.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump $(ANSIBLE_TRACE_ARGS) $(EXTRA_ARGS)

converge-paperless:
	$(MAKE) preflight WORKFLOW=converge-paperless
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/paperless.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/paperless.yml

converge-redpanda:
	$(MAKE) preflight WORKFLOW=converge-redpanda
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/redpanda.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-changedetection:
	$(MAKE) preflight WORKFLOW=converge-changedetection
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/changedetection.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-crawl4ai:
	$(MAKE) preflight WORKFLOW=converge-crawl4ai
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/crawl4ai.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-gitea:
	$(MAKE) preflight WORKFLOW=converge-gitea
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/gitea.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump $(ANSIBLE_TRACE_ARGS)

converge-gotenberg:
	$(MAKE) preflight WORKFLOW=converge-gotenberg
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/gotenberg.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-typesense:
	$(MAKE) preflight WORKFLOW=converge-typesense
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/typesense.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-control-plane-recovery:
	$(MAKE) preflight WORKFLOW=converge-control-plane-recovery
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/control-plane-recovery.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-netbox:
	$(MAKE) preflight WORKFLOW=converge-netbox
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/netbox.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-searxng:
	$(MAKE) preflight WORKFLOW=converge-searxng
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/searxng.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/searxng.yml

converge-ollama:
	$(MAKE) preflight WORKFLOW=converge-ollama
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/ollama.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/ollama.yml

converge-one-api:
	$(MAKE) preflight WORKFLOW=converge-one-api
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/one-api.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-piper:
	$(MAKE) preflight WORKFLOW=converge-piper
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/piper.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-matrix-synapse:
	$(MAKE) preflight WORKFLOW=converge-matrix-synapse
	uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate
	$(MAKE) generate-edge-static-sites
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/matrix-synapse.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/matrix-synapse.yml

converge-n8n:
	$(MAKE) preflight WORKFLOW=converge-n8n
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/n8n.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/n8n.yml

converge-nextcloud:
	$(MAKE) preflight WORKFLOW=converge-nextcloud
	$(MAKE) generate-edge-static-sites
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/nextcloud.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/nextcloud.yml

converge-nomad:
	$(MAKE) preflight WORKFLOW=converge-nomad
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/nomad.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump $(ANSIBLE_TRACE_ARGS)

converge-dozzle:
	$(MAKE) preflight WORKFLOW=converge-dozzle
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/dozzle.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/dozzle.yml

converge-realtime:
	$(MAKE) preflight WORKFLOW=converge-realtime
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/realtime.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-open-webui:
	$(MAKE) preflight WORKFLOW=converge-open-webui
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/open-webui.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/open-webui.yml

converge-serverclaw:
	$(MAKE) preflight WORKFLOW=converge-serverclaw
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/serverclaw.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-litellm:
	$(MAKE) preflight WORKFLOW=converge-litellm
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/litellm.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-librechat:
	$(MAKE) preflight WORKFLOW=converge-librechat
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/librechat.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-homepage:
	$(MAKE) preflight WORKFLOW=converge-homepage
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/homepage.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

# Refresh all discovery surfaces (home.lv3.org, ops.lv3.org, wiki.lv3.org).
# Run after any service deployment to eliminate drift between the service
# catalog and operator-facing portals.  See ADR 0383.
# Usage:
#   make refresh-discovery-surfaces env=production
#   make refresh-discovery-surfaces env=production trigger_service=neko
#   make refresh-discovery-surfaces env=production refresh_homepage=false
refresh-discovery-surfaces:
	$(MAKE) preflight WORKFLOW=refresh-discovery-surfaces
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook \
		-i $(REPO_ROOT)/inventory/ \
		$(REPO_ROOT)/playbooks/refresh-discovery-surfaces.yml \
		-e env=$(env) \
		--private-key $(BOOTSTRAP_KEY) \
		-e proxmox_guest_ssh_connection_mode=proxmox_host_jump \
		-e ops_portal_repo_root=$(REPO_ROOT) \
		$(if $(trigger_service),-e trigger_service=$(trigger_service)) \
		$(if $(refresh_homepage),-e refresh_homepage=$(refresh_homepage)) \
		$(if $(refresh_ops_portal),-e refresh_ops_portal=$(refresh_ops_portal)) \
		$(if $(refresh_outline),-e refresh_outline=$(refresh_outline))

converge-excalidraw:
	$(MAKE) preflight WORKFLOW=converge-excalidraw
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/excalidraw.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e @$(REPO_ROOT)/playbooks/vars/excalidraw.yml

converge-rag-context:
	$(MAKE) preflight WORKFLOW=converge-rag-context
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/rag-context.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump $(ANSIBLE_TRACE_ARGS)

converge-portainer:
	$(MAKE) preflight WORKFLOW=converge-portainer
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/portainer.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-vaultwarden:
	$(MAKE) preflight WORKFLOW=converge-vaultwarden
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/vaultwarden.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-mattermost:
	$(MAKE) preflight WORKFLOW=converge-mattermost
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/mattermost.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

rotate-secret:
	$(MAKE) preflight WORKFLOW=rotate-secret
	@test -n "$(SECRET_ID)" || (echo "set SECRET_ID=<secret-id>"; exit 1)
	python3 $(REPO_ROOT)/scripts/secret_rotation.py --secret $(SECRET_ID) $(ROTATION_ARGS)

token-inventory-audit:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/token_lifecycle.py audit $(TOKEN_LIFECYCLE_ARGS)

token-exposure-response:
	@test -n "$(TOKEN_ID)" || (echo "set TOKEN_ID=<token-id>"; exit 1)
	uv run --with pyyaml python $(REPO_ROOT)/scripts/token_lifecycle.py exposure-response --token-id "$(TOKEN_ID)" $(if $(EXPOSURE_SOURCE),--exposure-source "$(EXPOSURE_SOURCE)",) $(if $(EXPOSURE_NOTES),--notes "$(EXPOSURE_NOTES)",) $(TOKEN_LIFECYCLE_ARGS)

rotate-keycloak-client-secret:
	@test -n "$(TOKEN_ID)" || (echo "set TOKEN_ID=<token-id>"; exit 1)
	uv run --with pyyaml python $(REPO_ROOT)/scripts/token_lifecycle.py rotate --token-id "$(TOKEN_ID)" $(TOKEN_LIFECYCLE_ARGS)

rotate-windmill-token:
	@test -n "$(TOKEN_ID)" || (echo "set TOKEN_ID=<token-id>"; exit 1)
	uv run --with pyyaml python $(REPO_ROOT)/scripts/token_lifecycle.py rotate --token-id "$(TOKEN_ID)" $(TOKEN_LIFECYCLE_ARGS)

rotate-grafana-service-token:
	@test -n "$(TOKEN_ID)" || (echo "set TOKEN_ID=<token-id>"; exit 1)
	uv run --with pyyaml python $(REPO_ROOT)/scripts/token_lifecycle.py rotate --token-id "$(TOKEN_ID)" $(TOKEN_LIFECYCLE_ARGS)

rotate-platform-cli-token:
	@test -n "$(TOKEN_ID)" || (echo "set TOKEN_ID=<token-id>"; exit 1)
	uv run --with pyyaml python $(REPO_ROOT)/scripts/token_lifecycle.py rotate --token-id "$(TOKEN_ID)" $(TOKEN_LIFECYCLE_ARGS)

deploy-uptime-kuma:
	$(MAKE) preflight WORKFLOW=deploy-uptime-kuma
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/uptime-kuma.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

uptime-kuma-manage:
	$(MAKE) preflight WORKFLOW=uptime-kuma-manage
	@test -n "$(ACTION)" || (echo "set ACTION=<bootstrap|ensure-monitors|ensure-status-page|list-monitors|list-maintenances>"; exit 1)
	$(UPTIME_KUMA_PYTHON) $(REPO_ROOT)/scripts/uptime_kuma_tool.py $(ACTION) --auth-file "$(UPTIME_KUMA_AUTH_FILE)" $(UPTIME_KUMA_ARGS)

uptime-robot-manage:
	$(MAKE) preflight WORKFLOW=uptime-robot-manage
	@test -n "$(ACTION)" || (echo "set ACTION=<ensure|list-monitors>"; exit 1)
	$(PYTHON3) $(REPO_ROOT)/scripts/uptime_robot_tool.py $(ACTION) $(UPTIME_ROBOT_ARGS)

coolify-manage:
	$(MAKE) preflight WORKFLOW=coolify-manage
	@test -n "$(ACTION)" || (echo "set ACTION=<whoami|list-applications|deploy-repo>"; exit 1)
	uv run --with pyyaml python $(REPO_ROOT)/scripts/coolify_tool.py $(ACTION) $(COOLIFY_ARGS)

deploy-repo-profile:
	$(MAKE) preflight WORKFLOW=deploy-repo-profile
	@test -n "$(PROFILE)" || (echo "set PROFILE=<repo-deploy-profile-id>"; exit 1)
	uv run --with pyyaml python $(REPO_ROOT)/scripts/repo_deploy_profiles.py deploy "$(PROFILE)" $(DEPLOY_PROFILE_ARGS)

portainer-manage:
	$(MAKE) preflight WORKFLOW=portainer-manage
	@test -n "$(ACTION)" || (echo "set ACTION=<whoami|list-containers|container-logs|restart-container>"; exit 1)
	uvx --from requests python $(REPO_ROOT)/scripts/portainer_tool.py $(ACTION) $(PORTAINER_ARGS)

semaphore-manage:
	$(MAKE) preflight WORKFLOW=semaphore-manage
	@test -n "$(ACTION)" || (echo "set ACTION=<whoami|list-projects|list-templates|run-template|task-output>"; exit 1)
	$(PYTHON3) $(REPO_ROOT)/scripts/semaphore_tool.py $(ACTION) $(SEMAPHORE_ARGS)

woodpecker-manage:
	$(MAKE) preflight WORKFLOW=woodpecker-manage
	@test -n "$(ACTION)" || (echo "set ACTION=<whoami|list-repos|activate-repo|list-secrets|upsert-secret|list-pipelines|trigger-pipeline>"; exit 1)
	uv run --with pyyaml python $(REPO_ROOT)/scripts/woodpecker_tool.py --auth-file $(LOCAL_OVERLAY_ROOT)/woodpecker/admin-auth.json $(ACTION) $(WOODPECKER_ARGS)

plane-manage:
	$(MAKE) preflight WORKFLOW=plane-manage
	@test -n "$(ACTION)" || (echo "set ACTION=<whoami|list-workspaces|list-projects|list-issues|create-issue|sync-adrs>"; exit 1)
	uv run --with pyyaml python $(REPO_ROOT)/scripts/plane_tool.py --auth-file $(LOCAL_OVERLAY_ROOT)/plane/admin-auth.json $(ACTION) $(PLANE_ARGS)

configure-backups:
	$(MAKE) preflight WORKFLOW=configure-backups
	PROXMOX_BACKUP_CIFS_SERVER=$${PROXMOX_BACKUP_CIFS_SERVER:?set PROXMOX_BACKUP_CIFS_SERVER} \
	PROXMOX_BACKUP_CIFS_SHARE=$${PROXMOX_BACKUP_CIFS_SHARE:?set PROXMOX_BACKUP_CIFS_SHARE} \
	PROXMOX_BACKUP_CIFS_USERNAME=$${PROXMOX_BACKUP_CIFS_USERNAME:?set PROXMOX_BACKUP_CIFS_USERNAME} \
	PROXMOX_BACKUP_CIFS_PASSWORD=$${PROXMOX_BACKUP_CIFS_PASSWORD:?set PROXMOX_BACKUP_CIFS_PASSWORD} \
	$(ANSIBLE_PLAYBOOK_CMD) -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags storage,backups

configure-backup-vm:
	$(MAKE) preflight WORKFLOW=configure-backup-vm
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/backup-vm.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY)

configure-artifact-cache-vm:
	$(MAKE) preflight WORKFLOW=configure-artifact-cache-vm
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/artifact-cache-vm.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY)

database-dns:
	$(MAKE) preflight WORKFLOW=database-dns
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	$(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/database-dns.yml --env $(env) --

route-dns-assertion-ledger:
	$(MAKE) preflight WORKFLOW=route-dns-assertion-ledger
	uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --validate
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	$(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/route-dns-assertion-ledger.yml --env $(env) --

provision-subdomain:
	@test -n "$(FQDN)" || (echo "set FQDN=<hostname>"; exit 1)
	$(MAKE) preflight WORKFLOW=provision-subdomain
	uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_catalog.py --fqdn "$(FQDN)" --provision-check
	$(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/provision-subdomain.yml --env $(env) -- -e subdomain_fqdn="$(FQDN)" $(EXTRA_ARGS)
	@if [ "$$(uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_catalog.py --fqdn "$(FQDN)" --print-field route_mode)" = "edge" ]; then \
		$(MAKE) configure-edge-publication EXTRA_ARGS="$(EXTRA_ARGS)"; \
	fi

start-workstream:
	@test -n "$(WORKSTREAM)" || (echo "set WORKSTREAM=<workstream-id>"; exit 1)
	$(REPO_ROOT)/scripts/create-workstream.sh $(WORKSTREAM)

capacity-report:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/capacity_report.py --model $(REPO_ROOT)/config/capacity-model.json --format $(or $(FORMAT),text) $(if $(filter true,$(NO_LIVE_METRICS)),--no-live-metrics,) $(CAPACITY_ARGS)

weekly-capacity-report:
	uv run --with pyyaml python $(REPO_ROOT)/config/windmill/scripts/weekly-capacity-report.py --repo-path $(REPO_ROOT) $(if $(filter true,$(NO_LIVE_METRICS)),--no-live-metrics,)

disk-space-monitor:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/disk_metrics.py $(if $(JSON),--json,) $(if $(VM),--vm $(VM),) $(if $(THRESHOLD),--threshold $(THRESHOLD),)

k6-smoke:
	uv run --with pyyaml --with nats-py python $(REPO_ROOT)/scripts/k6_load_testing.py --repo-root $(REPO_ROOT) --scenario smoke $(K6_ARGS)

k6-load:
	uv run --with pyyaml --with nats-py python $(REPO_ROOT)/scripts/k6_load_testing.py --repo-root $(REPO_ROOT) --scenario load --publish-nats --notify-ntfy $(K6_ARGS)

k6-soak:
	uv run --with pyyaml --with nats-py python $(REPO_ROOT)/scripts/k6_load_testing.py --repo-root $(REPO_ROOT) --scenario soak --publish-nats --notify-ntfy $(K6_ARGS)

immutable-guest-replacement-plan:
	@if [ -n "$(service)" ]; then \
		uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/immutable_guest_replacement.py --service "$(service)"; \
	elif [ -n "$(guest)" ]; then \
		uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/immutable_guest_replacement.py --guest "$(guest)"; \
	else \
		echo "set service=<service-id> or guest=<guest-name>"; exit 1; \
	fi

check-nats-streams:
	uv run --with pyyaml --with nats-py python $(REPO_ROOT)/scripts/nats_streams.py

apply-nats-streams:
	uv run --with pyyaml --with nats-py python $(REPO_ROOT)/scripts/nats_streams.py --apply

merge-config-changes:
	$(MAKE) preflight WORKFLOW=merge-config-changes
	python3 $(REPO_ROOT)/scripts/config_merge_protocol.py --repo-root $(REPO_ROOT) merge --dsn "$${LV3_CONFIG_MERGE_DSN:-$${DATABASE_URL:-}}" $(if $(FILE),--file "$(FILE)",) $(if $(filter true,$(PUBLISH_NATS)),--publish-nats,) $(MERGE_ARGS)

promote:
	@test -n "$(SERVICE)" || (echo "set SERVICE=<service-id>"; exit 1)
	@test -n "$(STAGING_RECEIPT)" || (echo "set STAGING_RECEIPT=receipts/live-applies/staging/<receipt>.json"; exit 1)
	$(AUTOMATION_UV_PYTHON) $(REPO_ROOT)/scripts/promotion_pipeline.py --promote --service "$(SERVICE)" --staging-receipt "$(STAGING_RECEIPT)" --requester-class "$(REQUESTER_CLASS)" --approver-classes "$(APPROVER_CLASSES)" $(if $(BRANCH),--branch "$(BRANCH)",) $(if $(EXTRA_ARGS),--extra-args "$(EXTRA_ARGS)",) $(if $(filter true,$(DRY_RUN)),--dry-run,)

live-apply-group:
	@test -n "$(group)" || (echo "set group=<group-id>"; exit 1)
	$(MAKE) preflight WORKFLOW=live-apply-group
	$(MAKE) check-canonical-truth
	uvx --from pyyaml python $(REPO_ROOT)/scripts/interface_contracts.py --check-live-apply "group:$(group)"
	@if [ "$(env)" = "production" ] && printf '%s' "$(EXTRA_ARGS)" | grep -Eq '(^|[[:space:]])bypass_promotion=true([[:space:]]|$$)'; then \
		$(AUTOMATION_UV_PYTHON) $(REPO_ROOT)/scripts/promotion_pipeline.py --emit-bypass-event --service "group:$(group)" --actor-id "$${USER:-unknown}" --correlation-id "break-glass:group:$(group):$$(date -u +%Y%m%dT%H%M%SZ)"; \
	fi
	@if [ "$(env)" = "production" ]; then $(AUTOMATION_UV_PYTHON) $(REPO_ROOT)/scripts/vulnerability_budget.py --all; fi
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/service_redundancy.py --check-live-apply
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/groups/$(group).yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump $(ANSIBLE_TRACE_ARGS) $(EXTRA_ARGS)
	uv run --with pyyaml python $(REPO_ROOT)/scripts/trigger_restic_live_apply.py --env $(env) --mode backup --triggered-by live-apply-group --live-apply-trigger

live-apply-service:
	@test -n "$(service)" || (echo "set service=<service-id>"; exit 1)
	$(MAKE) preflight WORKFLOW=live-apply-service
	$(MAKE) check-canonical-truth
	uvx --from pyyaml python $(REPO_ROOT)/scripts/interface_contracts.py --check-live-apply "service:$(service)"
	@if [ "$(env)" = "production" ] && printf '%s' "$(EXTRA_ARGS)" | grep -Eq '(^|[[:space:]])bypass_promotion=true([[:space:]]|$$)'; then \
		$(AUTOMATION_UV_PYTHON) $(REPO_ROOT)/scripts/promotion_pipeline.py --emit-bypass-event --service "$(service)" --actor-id "$${USER:-unknown}" --correlation-id "break-glass:service:$(service):$$(date -u +%Y%m%dT%H%M%SZ)"; \
	fi
	@if uv run --with pyyaml python $(REPO_ROOT)/scripts/service_id_resolver.py --exists-in-catalog "$(service)" >/dev/null; then \
		set -e; \
		if [ "$(env)" = "production" ]; then $(AUTOMATION_UV_PYTHON) $(REPO_ROOT)/scripts/vulnerability_budget.py --service "$(service)"; fi; \
		uv run --with pyyaml python $(REPO_ROOT)/scripts/standby_capacity.py --service "$(service)"; \
		uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/service_redundancy.py --check-live-apply --service "$(service)"; \
		uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/immutable_guest_replacement.py --check-live-apply --service "$(service)" $(if $(filter true,$(ALLOW_IN_PLACE_MUTATION)),--allow-in-place-mutation,); \
	else \
		printf '%s\n' "INFO live-apply-service: skipping service-catalog gates for non-catalog playbook '$(service)'"; \
	fi
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/services/$(service).yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump $(if $(filter ops_portal,$(service)),-e ops_portal_repo_root=$(REPO_ROOT),) $(ANSIBLE_TRACE_ARGS) $(EXTRA_ARGS)
	uv run --with pyyaml python $(REPO_ROOT)/scripts/trigger_restic_live_apply.py --env $(env) --mode backup --triggered-by live-apply-service --live-apply-trigger

live-apply-site:
	$(MAKE) preflight WORKFLOW=live-apply-site
	$(MAKE) check-canonical-truth
	uvx --from pyyaml python $(REPO_ROOT)/scripts/interface_contracts.py --check-live-apply "site:site"
	@if [ "$(env)" = "production" ] && printf '%s' "$(EXTRA_ARGS)" | grep -Eq '(^|[[:space:]])bypass_promotion=true([[:space:]]|$$)'; then \
		$(AUTOMATION_UV_PYTHON) $(REPO_ROOT)/scripts/promotion_pipeline.py --emit-bypass-event --service "site" --actor-id "$${USER:-unknown}" --correlation-id "break-glass:site:$$(date -u +%Y%m%dT%H%M%SZ)"; \
	fi
	@if [ "$(env)" = "production" ]; then $(AUTOMATION_UV_PYTHON) $(REPO_ROOT)/scripts/vulnerability_budget.py --all; fi
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/service_redundancy.py --check-live-apply
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/site.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump $(ANSIBLE_TRACE_ARGS) $(EXTRA_ARGS)
	uv run --with pyyaml python $(REPO_ROOT)/scripts/trigger_restic_live_apply.py --env $(env) --mode backup --triggered-by live-apply-site --live-apply-trigger

live-apply-waves:
	@test -n "$(manifest)" || (echo "set manifest=config/dependency-waves/<plan>.yaml"; exit 1)
	$(MAKE) preflight WORKFLOW=live-apply-waves
	uv run --with pyyaml python $(REPO_ROOT)/scripts/dependency_wave_apply.py --manifest "$(manifest)" --env "$(or $(env),production)" $(if $(CATALOG),--catalog "$(CATALOG)",) $(if $(EXTRA_ARGS),--extra-args "$(EXTRA_ARGS)",) $(WAVE_ARGS)
	uv run --with pyyaml python $(REPO_ROOT)/scripts/trigger_restic_live_apply.py --env "$(or $(env),production)" --mode backup --triggered-by live-apply-waves --live-apply-trigger

live-apply-train-status:
	$(AUTOMATION_UV_PYTHON) $(REPO_ROOT)/scripts/live_apply_merge_train.py --repo-root $(REPO_ROOT) status

live-apply-train-queue:
	@test -n "$(WORKSTREAMS)" || (echo 'set WORKSTREAMS="id-a id-b"'; exit 1)
	$(AUTOMATION_UV_PYTHON) $(REPO_ROOT)/scripts/live_apply_merge_train.py --repo-root $(REPO_ROOT) queue $(foreach ws,$(WORKSTREAMS),--workstream "$(ws)") --requested-by "$${USER:-unknown}"

live-apply-train-plan:
	$(AUTOMATION_UV_PYTHON) $(REPO_ROOT)/scripts/live_apply_merge_train.py --repo-root $(REPO_ROOT) plan $(foreach ws,$(WORKSTREAMS),--workstream "$(ws)")

live-apply-train-bundle:
	$(AUTOMATION_UV_PYTHON) $(REPO_ROOT)/scripts/live_apply_merge_train.py --repo-root $(REPO_ROOT) bundle $(foreach ws,$(WORKSTREAMS),--workstream "$(ws)")

live-apply-train-run:
	$(AUTOMATION_UV_PYTHON) $(REPO_ROOT)/scripts/live_apply_merge_train.py --repo-root $(REPO_ROOT) run $(foreach ws,$(WORKSTREAMS),--workstream "$(ws)") --requested-by "$${USER:-unknown}" $(if $(filter true,$(NO_AUTO_ROLLBACK)),--no-auto-rollback,)

live-apply-train-rollback:
	@test -n "$(BUNDLE)" || (echo "set BUNDLE=receipts/rollback-bundles/<bundle>.json"; exit 1)
	$(AUTOMATION_UV_PYTHON) $(REPO_ROOT)/scripts/live_apply_merge_train.py --repo-root $(REPO_ROOT) rollback --bundle "$(BUNDLE)"

## Remote build execution (ADR 0082)
.PHONY: remote-lint remote-validate remote-pre-push remote-packer-build remote-image-build remote-exec check-build-server remote-tofu-plan remote-tofu-apply tofu-drift tofu-import

remote-lint:
	$(REPO_ROOT)/scripts/remote_exec.sh remote-lint --local-fallback

remote-validate:
	$(REPO_ROOT)/scripts/remote_exec.sh remote-validate --local-fallback

remote-pre-push:
	$(REPO_ROOT)/scripts/remote_exec.sh remote-pre-push --local-fallback

remote-packer-build:
	@test -n "$(IMAGE)" || (echo "set IMAGE=<name>"; exit 1)
	IMAGE="$(IMAGE)" $(REPO_ROOT)/scripts/remote_exec.sh remote-packer-build --local-fallback

remote-packer-validate:
	$(REPO_ROOT)/scripts/remote_exec.sh remote-packer-validate --local-fallback

validate-packer: remote-packer-validate

packer-template-rebuild:
	python3 $(REPO_ROOT)/config/windmill/scripts/packer-template-rebuild.py

remote-image-build:
	@test -n "$(SERVICE)" || (echo "set SERVICE=<service-id>"; exit 1)
	$(RUN_ID_ENV) SERVICE="$(SERVICE)" COMMAND="$(COMMAND)" $(REPO_ROOT)/scripts/remote_exec.sh remote-image-build --local-fallback

remote-exec:
	@test -n "$(COMMAND)" || (echo "set COMMAND=<shell-command>"; exit 1)
	$(RUN_ID_ENV) COMMAND="$(COMMAND)" $(REPO_ROOT)/scripts/remote_exec.sh remote-exec --local-fallback

check-build-server:
	$(REPO_ROOT)/scripts/remote_exec.sh check-build-server

remote-tofu-plan:
	@test -n "$(ENV)" || (echo "set ENV=<production|staging>"; exit 1)
	@COMMAND="$$(python3 $(REPO_ROOT)/scripts/tofu_remote_command.py plan $(ENV))" \
		$(RUN_ID_ENV) $(REPO_ROOT)/scripts/remote_exec.sh remote-exec

remote-tofu-apply:
	@test -n "$(ENV)" || (echo "set ENV=<production|staging>"; exit 1)
	@COMMAND="$$(python3 $(REPO_ROOT)/scripts/tofu_remote_command.py apply $(ENV))" \
		$(RUN_ID_ENV) $(REPO_ROOT)/scripts/remote_exec.sh remote-exec

tofu-drift:
	@test -n "$(ENV)" || (echo "set ENV=<production|staging>"; exit 1)
	@COMMAND="$$(python3 $(REPO_ROOT)/scripts/tofu_remote_command.py drift $(ENV))" \
		$(RUN_ID_ENV) $(REPO_ROOT)/scripts/remote_exec.sh remote-exec

tofu-import:
	@test -n "$(VM)" || (echo "set VM=<vm-name>"; exit 1)
	@test "$(ENV)" = "production" || (echo "tofu-import currently supports ENV=production"; exit 1)
	@COMMAND="$$(python3 $(REPO_ROOT)/scripts/tofu_remote_command.py import $(ENV) --vm $(VM))" \
		$(RUN_ID_ENV) $(REPO_ROOT)/scripts/remote_exec.sh remote-exec

# ADR Governance Commands
validate-adr-transitions:
	python3 $(REPO_ROOT)/scripts/validate_adr_status_transitions.py

sync-adrs-to-plane:
	python3 $(REPO_ROOT)/scripts/sync_adrs_to_plane.py

sync-adrs-to-plane-dry-run:
	python3 $(REPO_ROOT)/scripts/sync_adrs_to_plane.py --dry-run

run-adr-quarterly-audit:
	python3 $(REPO_ROOT)/config/windmill/scripts/adr-quarterly-audit.py

run-adr-quarterly-audit-dry-run:
	python3 $(REPO_ROOT)/config/windmill/scripts/adr-quarterly-audit.py --dry-run

# ADR Governance Provisioning (IaC)
provision-adr-governance:
	@test -n "$(PLANE_ADMIN_TOKEN)" || (echo "PLANE_ADMIN_TOKEN required: make provision-adr-governance PLANE_ADMIN_TOKEN=your_token"; exit 1)
	ansible-playbook $(REPO_ROOT)/playbooks/provision_adr_governance.yml \
		-i $(ANSIBLE_INVENTORY) \
		-e "plane_admin_bootstrap_token=$(PLANE_ADMIN_TOKEN)"

provision-adr-governance-dry-run:
	@test -n "$(PLANE_ADMIN_TOKEN)" || (echo "PLANE_ADMIN_TOKEN required: make provision-adr-governance-dry-run PLANE_ADMIN_TOKEN=your_token"; exit 1)
	ansible-playbook $(REPO_ROOT)/playbooks/provision_adr_governance.yml \
		-i $(ANSIBLE_INVENTORY) \
		-e "plane_admin_bootstrap_token=$(PLANE_ADMIN_TOKEN)" \
		--check

# =============================================================================
# Bootstrap — ADR 0386
# =============================================================================

init-local: ## Initialize .local/ overlay with SSH keys and secrets
	@if [ "$(FORCE)" = "true" ]; then \
		python3 $(REPO_ROOT)/scripts/init_local_overlay.py --force; \
	else \
		python3 $(REPO_ROOT)/scripts/init_local_overlay.py; \
	fi

generate-local-example: ## Regenerate local-overlay-template/ scaffold from secret manifest
	python3 $(REPO_ROOT)/scripts/init_local_overlay.py --generate-example

bootstrap: ## Full platform bootstrap from bare Debian 13 (ADR 0386)
	@echo "=== Stage 1: Local overlay initialization ==="
	@if [ ! -d "$(LOCAL_OVERLAY_ROOT)" ]; then \
		$(MAKE) init-local; \
	else \
		echo "  .local/ exists — skipping init (use FORCE=true to regenerate missing files)"; \
	fi
	@echo ""
	@echo "=== Stage 2: Proxmox VE installation ==="
	$(MAKE) install-proxmox
	$(MAKE) verify-bootstrap-proxmox
	@echo ""
	@echo "=== Stage 3: Network and access ==="
	$(MAKE) configure-network
	$(MAKE) harden-access
	@echo ""
	@echo "=== Stage 4: Guest provisioning ==="
	$(MAKE) provision-guests
	$(MAKE) verify-bootstrap-guests
	@echo ""
	@echo "=== Stage 5: Platform convergence ==="
	$(MAKE) converge-site
	$(MAKE) verify-platform
	@echo ""
	@echo "=== Bootstrap complete ==="

bootstrap-minimal: ## Bootstrap critical path only (PG + Keycloak + Nginx + OpenBao)
	@echo "=== Minimal bootstrap: critical path only ==="
	@if [ ! -d "$(LOCAL_OVERLAY_ROOT)" ]; then \
		$(MAKE) init-local; \
	else \
		echo "  .local/ exists — skipping init"; \
	fi
	$(MAKE) install-proxmox
	$(MAKE) verify-bootstrap-proxmox
	$(MAKE) configure-network
	$(MAKE) provision-guests
	$(MAKE) verify-bootstrap-guests
	$(MAKE) converge-postgres-vm
	$(MAKE) converge-keycloak
	$(MAKE) converge-openbao
	$(MAKE) converge-api-gateway
	@echo ""
	@echo "=== Minimal bootstrap complete (PG, Keycloak, OpenBao, API Gateway) ==="

verify-bootstrap-proxmox: ## Verify Proxmox VE is installed and operational
	$(ANSIBLE_PLAYBOOK_CMD) -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/verify-bootstrap-proxmox.yml --private-key $(BOOTSTRAP_KEY) $(ANSIBLE_TRACE_ARGS)

verify-bootstrap-guests: ## Verify all guest VMs are reachable
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_PLAYBOOK_CMD) -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/verify-bootstrap-guests.yml --private-key $(BOOTSTRAP_KEY) $(ANSIBLE_TRACE_ARGS)

verify-platform: ## Verify critical platform services are healthy
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_PLAYBOOK_CMD) -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/verify-platform.yml --private-key $(BOOTSTRAP_KEY) $(ANSIBLE_TRACE_ARGS)

converge-site: ## Full site convergence (all services)
	$(MAKE) preflight WORKFLOW=converge-site
	$(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/collections/ansible_collections/lv3/platform/playbooks/site.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) $(EXTRA_ARGS)

# =============================================================================
# Docker Development Environment — ADR 0387
# =============================================================================

docker-dev-up: ## Start minimal Docker dev environment (Tier 1)
	@test -f "$(LOCAL_OVERLAY_ROOT)/ssh/bootstrap.id_ed25519.pub" || (echo "Run 'make init-local' first to generate SSH keys"; exit 1)
	docker compose -f $(REPO_ROOT)/docker-dev/minimal/docker-compose.yml up -d --build
	@echo "Waiting for containers to initialize..."
	@sleep 5
	$(MAKE) docker-dev-verify

docker-dev-up-full: ## Start full-topology Docker dev environment (Tier 2)
	@test -f "$(LOCAL_OVERLAY_ROOT)/ssh/bootstrap.id_ed25519.pub" || (echo "Run 'make init-local' first to generate SSH keys"; exit 1)
	docker compose -f $(REPO_ROOT)/docker-dev/full/docker-compose.yml up -d --build
	@echo "Waiting for containers to initialize..."
	@sleep 5
	$(MAKE) docker-dev-verify

docker-dev-down: ## Stop Docker dev environment
	docker compose -f $(REPO_ROOT)/docker-dev/minimal/docker-compose.yml down 2>/dev/null || true
	docker compose -f $(REPO_ROOT)/docker-dev/full/docker-compose.yml down 2>/dev/null || true

docker-dev-verify: ## Verify Docker dev containers are SSH-reachable
	@echo "Checking SSH access to containers..."
	@for host in 10.10.10.10 10.10.10.50 10.10.10.92; do \
		if ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=5 \
			-i $(LOCAL_OVERLAY_ROOT)/ssh/bootstrap.id_ed25519 ops@$$host "echo OK" 2>/dev/null; then \
			echo "  OK $$host"; \
		else \
			echo "  FAIL $$host"; \
		fi; \
	done

docker-dev-converge: ## Run Ansible convergence against Docker dev containers
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_PLAYBOOK_CMD) \
		-i $(REPO_ROOT)/inventory/hosts-docker.yml \
		$(REPO_ROOT)/collections/ansible_collections/lv3/platform/playbooks/site.yml \
		--private-key $(LOCAL_OVERLAY_ROOT)/ssh/bootstrap.id_ed25519 \
		$(ANSIBLE_TRACE_ARGS) $(EXTRA_ARGS)

docker-dev-reset: ## Destroy and recreate Docker dev environment
	$(MAKE) docker-dev-down
	docker volume ls -q --filter name=serverclaw | xargs -r docker volume rm 2>/dev/null || true
	$(MAKE) docker-dev-up

# =============================================================================
# Publication — sync to public ServerClaw repo
# =============================================================================

publish-serverclaw: ## Dry-run: sanitize repo and check for leaks (no push)
	uv run --with pyyaml python3 $(REPO_ROOT)/scripts/publish_to_serverclaw.py

publish-serverclaw-push: ## Sanitize and push to public ServerClaw repo
	uv run --with pyyaml python3 $(REPO_ROOT)/scripts/publish_to_serverclaw.py --push

audit-sanitization: ## Check publication sanitization coverage for drift
	uv run --with pyyaml python3 $(REPO_ROOT)/scripts/audit_sanitization_coverage.py

audit-sanitization-strict: ## Same as audit-sanitization but exit 1 on any gap
	uv run --with pyyaml python3 $(REPO_ROOT)/scripts/audit_sanitization_coverage.py --strict
