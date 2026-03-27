REPO_ROOT := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
ANSIBLE_INVENTORY := $(REPO_ROOT)/inventory/hosts.yml
BOOTSTRAP_KEY ?= /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519
ANSIBLE_LOCAL_TEMP ?= /tmp/proxmox_florin_server-ansible-local
ANSIBLE_REMOTE_TEMP ?= /tmp
ANSIBLE_ENV := ANSIBLE_LOCAL_TEMP=$(ANSIBLE_LOCAL_TEMP) ANSIBLE_REMOTE_TEMP=$(ANSIBLE_REMOTE_TEMP)
ANSIBLE_SCOPED_RUN = $(RUN_ID_ENV) ANSIBLE_REMOTE_TEMP=$(ANSIBLE_REMOTE_TEMP) $(REPO_ROOT)/scripts/run_with_namespace.sh uvx --from pyyaml python $(REPO_ROOT)/scripts/ansible_scope_runner.py run --inventory $(ANSIBLE_INVENTORY) $(if $(strip $(PLATFORM_TRACE_ID)),--run-id $(PLATFORM_TRACE_ID),)
UPTIME_KUMA_PYTHON ?= $(REPO_ROOT)/.local/uptime-kuma/client-venv/bin/python
ACTION ?= list-monitors
UPTIME_KUMA_ARGS ?=
PORTAINER_ARGS ?=
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
EXCEPTION_OWNER ?=
EXCEPTION_REVIEW_BY ?=
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
CHECK_RUNNER_REGISTRY ?= registry.lv3.org/check-runner
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

.PHONY: prepare-run-namespace validate validate-generated-vars validate-ansible-syntax validate-yaml validate-role-argument-specs validate-ansible-lint validate-ansible-idempotency validate-shell validate-json validate-compose-runtime-envs validate-data-models validate-interface-contracts validate-health-probes validate-alert-rules validate-tofu generate-platform-vars show-platform-facts generate-slo-rules validate-generated-slo generate-status-docs assemble-canonical-truth check-canonical-truth generate-platform-manifest generate-status generate-ops-portal generate-changelog-portal generate-dependency-diagram generate-uptime-kuma-monitors validate-generated-uptime-kuma-monitors docs deploy-ops-portal deploy-changelog-portal deploy-docs-portal validate-generated-docs validate-generated-portals receipts receipt-info workflows workflow-info commands command-info interface-contracts interface-contract-info services show-service environments environment-info lanes lane-info execution-lanes execution-lane-info api-publication api-publication-info agent-tools agent-tool-info export-mcp-tools check-image-freshness upgrade-container-image pin-image scaffold-service install-hooks pre-push-gate gate-status dr-status dr-runbook runbook-executor post-merge-gate integration-tests nightly-integration-tests scheduler-watchdog-loop intent-queue-dispatcher platform-observation-loop fault-injection triage-alert triage-calibration search-index-rebuild scan-published-artifacts setup preflight syntax-check syntax-check-monitoring syntax-check-ntfy syntax-check-ntopng syntax-check-api-gateway syntax-check-gitea syntax-check-guest-network-policy syntax-check-docker-runtime syntax-check-backup-vm syntax-check-control-plane-recovery syntax-check-uptime-kuma syntax-check-mail-platform syntax-check-openbao syntax-check-step-ca syntax-check-headscale syntax-check-semaphore syntax-check-windmill syntax-check-keycloak syntax-check-langfuse syntax-check-netbox syntax-check-searxng syntax-check-ollama syntax-check-n8n syntax-check-open-webui syntax-check-mattermost syntax-check-portainer syntax-check-vaultwarden syntax-check-rag-context syntax-check-secret-rotation syntax-check-dozzle collection-sync collection-build collection-publish collection-install check-platform-drift drift-report subdomain-exposure-audit security-posture-report security-headers-audit public-surface-security-scan open-maintenance-window close-maintenance-window ensure-resource-lock-registry resource-locks resource-lock-acquire resource-lock-release resource-lock-heartbeat operator-onboard operator-offboard sync-operators quarterly-access-review install-proxmox configure-network configure-staging-bridge configure-ingress configure-edge-publication configure-tailscale provision-guests harden-access harden-guest-access harden-security provision-api-access converge-guest-network-policy converge-monitoring converge-ntfy converge-ntopng converge-api-gateway converge-gitea converge-docker-runtime converge-postgres-vm converge-mail-platform converge-openbao converge-step-ca converge-headscale converge-semaphore converge-windmill converge-control-plane-recovery converge-keycloak converge-langfuse converge-netbox converge-searxng converge-ollama converge-n8n converge-open-webui converge-mattermost converge-portainer converge-vaultwarden converge-rag-context converge-dozzle rotate-secret token-inventory-audit token-exposure-response rotate-keycloak-client-secret rotate-windmill-token rotate-grafana-service-token rotate-platform-cli-token deploy-uptime-kuma uptime-kuma-manage uptime-robot-manage portainer-manage semaphore-manage configure-backups configure-backup-vm database-dns provision-subdomain start-workstream capacity-report weekly-capacity-report immutable-guest-replacement-plan check-nats-streams apply-nats-streams promote live-apply-group live-apply-service live-apply-site live-apply-waves live-apply-train-status live-apply-train-queue live-apply-train-plan live-apply-train-bundle live-apply-train-run live-apply-train-rollback build-check-runners push-check-runners run-checks warm-cache cache-status fixture-up fixture-down fixture-list fixture-reaper install-cli update-cli validate-packer remote-packer-validate packer-template-rebuild remote-tofu-plan remote-tofu-apply tofu-drift tofu-import

prepare-run-namespace:
	@$(RUN_ID_ENV) python3 $(REPO_ROOT)/scripts/run_namespace.py --repo-root "$(REPO_ROOT)" --ensure >/dev/null

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

validate-compose-runtime-envs:
	$(REPO_ROOT)/scripts/validate_repo.sh compose-runtime-envs

validate-data-models:
	$(REPO_ROOT)/scripts/validate_repo.sh data-models

validate-interface-contracts:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/interface_contracts.py --validate

install-hooks:
	mkdir -p "$$(git rev-parse --git-path hooks)"
	install -m 0755 $(REPO_ROOT)/.githooks/pre-push "$$(git rev-parse --git-path hooks)/pre-push"
	uvx --from pre-commit pre-commit install --install-hooks --hook-type pre-commit

pre-push-gate:
	$(REPO_ROOT)/scripts/remote_exec.sh pre-push-gate --local-fallback

gate-status:
	python3 $(REPO_ROOT)/scripts/gate_status.py

dr-status:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/generate_dr_report.py

dr-runbook:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/disaster_recovery_runbook.py

runbook-executor:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/runbook_executor.py $(RUNBOOK_EXECUTOR_ARGS)

post-merge-gate:
	python3 $(REPO_ROOT)/config/windmill/scripts/post-merge-gate.py --repo-path $(REPO_ROOT)

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
	python3 $(REPO_ROOT)/scripts/published_artifact_secret_scan.py --repo-root $(REPO_ROOT) --path build/search-index

fault-injection:
	uv run --with pyyaml python $(REPO_ROOT)/scripts/lv3_cli.py run fault-injection --approve-risk $(if $(FAULT_INJECTION_ARGS),--args $(FAULT_INJECTION_ARGS),)

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
	uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_exposure_audit.py --check-registry --include-live-dns --include-http-auth --include-hetzner-zone --write-receipt --print-report-json

## Ephemeral fixtures (ADR 0088)
fixture-up:
	python3 $(REPO_ROOT)/scripts/fixture_manager.py create $(if $(FIXTURE),"$(FIXTURE)") $(if $(PURPOSE),--purpose "$(PURPOSE)") $(if $(OWNER),--owner "$(OWNER)") $(if $(LIFETIME_HOURS),--lifetime-hours "$(LIFETIME_HOURS)") $(if $(EPHEMERAL_POLICY),--policy "$(EPHEMERAL_POLICY)") $(if $(ALLOW_EXTEND),--extend)

fixture-down:
	python3 $(REPO_ROOT)/scripts/fixture_manager.py destroy $(if $(FIXTURE),"$(FIXTURE)") $(if $(RECEIPT_ID),--receipt-id "$(RECEIPT_ID)") $(if $(VMID),--vmid "$(VMID)")

fixture-list:
	python3 $(REPO_ROOT)/scripts/fixture_manager.py list $(if $(NO_REFRESH_HEALTH),--no-refresh-health)

fixture-reaper:
	python3 $(REPO_ROOT)/config/windmill/scripts/ephemeral-vm-reaper.py

## Backup restore verification (ADR 0099)
restore-verification:
	python3 $(REPO_ROOT)/scripts/restore_verification.py $(RESTORE_ARGS)

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

generate-uptime-kuma-monitors:
	python3 $(REPO_ROOT)/scripts/uptime_contract.py --write

validate-generated-uptime-kuma-monitors:
	python3 $(REPO_ROOT)/scripts/uptime_contract.py --check

show-platform-facts:
	uvx --from ansible-core ansible-inventory -i $(ANSIBLE_INVENTORY) --host $(HOST) --yaml

validate-health-probes:
	$(REPO_ROOT)/scripts/validate_repo.sh health-probes

validate-alert-rules:
	$(REPO_ROOT)/scripts/validate_repo.sh alert-rules

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

upgrade-container-image:
	@test -n "$(IMAGE_ID)" || (echo "set IMAGE_ID=<image-id>"; exit 1)
	$(REPO_ROOT)/scripts/upgrade_container_image.py --image-id "$(IMAGE_ID)" $(if $(IMAGE_TAG),--tag "$(IMAGE_TAG)",) $(if $(filter true,$(WRITE)),--write,) $(if $(filter true,$(APPLY)),--apply,) $(if $(EXCEPTION_REASON),--exception-reason "$(EXCEPTION_REASON)",) $(if $(EXCEPTION_OWNER),--exception-owner "$(EXCEPTION_OWNER)",) $(if $(EXCEPTION_REVIEW_BY),--exception-review-by "$(EXCEPTION_REVIEW_BY)",)

pin-image:
	@test -n "$(IMAGE)" || (echo "set IMAGE=<registry/repository:tag>"; exit 1)
	python3 $(REPO_ROOT)/scripts/pin_image_ref.py --image "$(IMAGE)"

scaffold-service:
	@test -n "$(NAME)" || (echo "set NAME=<service-name>"; exit 1)
	uvx --from pyyaml python $(REPO_ROOT)/scripts/generate_service_scaffold.py --repo-root $(REPO_ROOT) --name "$(NAME)" --type "$(TYPE)" $(if $(DESCRIPTION),--description "$(DESCRIPTION)",) $(if $(CATEGORY),--category "$(CATEGORY)",) $(if $(VM),--vm "$(VM)",) $(if $(VMID),--vmid $(VMID),) $(if $(DEPENDS_ON),--depends-on "$(DEPENDS_ON)",) $(if $(PORT),--port $(PORT),) $(if $(SUBDOMAIN),--subdomain "$(SUBDOMAIN)",) $(if $(EXPOSURE),--exposure "$(EXPOSURE)",) --$(if $(filter true,$(OIDC)),,no-)oidc --$(if $(filter true,$(HAS_SECRETS)),,no-)has-secrets $(if $(IMAGE),--image "$(IMAGE)",)

generate-status-docs:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/generate_status_docs.py --write

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
	python3 $(REPO_ROOT)/scripts/published_artifact_secret_scan.py --repo-root $(REPO_ROOT) --path build/changelog-portal

scan-published-artifacts:
	python3 $(REPO_ROOT)/scripts/published_artifact_secret_scan.py --repo-root $(REPO_ROOT)

docs:
	uv run --with-requirements $(REPO_ROOT)/requirements/docs.txt python $(REPO_ROOT)/scripts/generate_docs_site.py --write
	uv run --with-requirements $(REPO_ROOT)/requirements/docs.txt mkdocs build --strict --config-file $(REPO_ROOT)/mkdocs.yml --site-dir $(REPO_ROOT)/build/docs-portal

deploy-ops-portal: generate-ops-portal
	$(MAKE) configure-edge-publication

deploy-changelog-portal: generate-changelog-portal
	$(MAKE) configure-edge-publication

deploy-docs-portal: docs
	$(MAKE) configure-edge-publication

generate-status: generate-slo-rules generate-status-docs generate-platform-manifest generate-ops-portal generate-changelog-portal docs

validate-generated-docs:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/generate_status_docs.py --check

validate-generated-portals:
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/generate_ops_portal.py --check
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/generate_changelog_portal.py --check
	uv run --with pyyaml python $(REPO_ROOT)/scripts/generate_slo_rules.py --check
	$(MAKE) docs

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

syntax-check-guest-network-policy:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/guest-network-policy.yml --syntax-check

syntax-check-docker-runtime:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/docker-runtime.yml --syntax-check

syntax-check-backup-vm:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/backup-vm.yml --syntax-check

syntax-check-control-plane-recovery:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/control-plane-recovery.yml --syntax-check

syntax-check-uptime-kuma:
	ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/uptime-kuma.yml --syntax-check

syntax-check-mail-platform:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/mail-platform.yml --syntax-check

syntax-check-openbao:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/openbao.yml --syntax-check

syntax-check-step-ca:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/step-ca.yml --syntax-check

syntax-check-semaphore:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/semaphore.yml --syntax-check

syntax-check-headscale:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/headscale.yml --syntax-check

syntax-check-windmill:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/windmill.yml --syntax-check

syntax-check-keycloak:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/keycloak.yml --syntax-check

syntax-check-langfuse:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/langfuse.yml --syntax-check

syntax-check-api-gateway:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/api-gateway.yml --syntax-check

syntax-check-gitea:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/gitea.yml --syntax-check

syntax-check-netbox:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/netbox.yml --syntax-check

syntax-check-searxng:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/searxng.yml --syntax-check

syntax-check-ollama:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/ollama.yml --syntax-check

syntax-check-n8n:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/n8n.yml --syntax-check
syntax-check-dozzle:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/dozzle.yml --syntax-check

syntax-check-open-webui:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/open-webui.yml --syntax-check

syntax-check-homepage:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/homepage.yml --syntax-check

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

configure-edge-publication:
	$(MAKE) preflight WORKFLOW=configure-edge-publication
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/public-edge.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump $(EXTRA_ARGS)

configure-tailscale:
	$(MAKE) preflight WORKFLOW=configure-tailscale
	$(ANSIBLE_PLAYBOOK_CMD) -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags tailscale

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
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/ntfy.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-ntopng:
	$(MAKE) preflight WORKFLOW=converge-ntopng
	$(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/ntopng.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY)

converge-docker-runtime:
	$(MAKE) preflight WORKFLOW=converge-docker-runtime
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/docker-runtime.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

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

converge-step-ca:
	$(MAKE) preflight WORKFLOW=converge-step-ca
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/step-ca.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-semaphore:
	$(MAKE) preflight WORKFLOW=converge-semaphore
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/semaphore.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-headscale:
	$(MAKE) preflight WORKFLOW=converge-headscale
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/headscale.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-windmill:
	$(MAKE) preflight WORKFLOW=converge-windmill
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/windmill.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-keycloak:
	$(MAKE) preflight WORKFLOW=converge-keycloak
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/keycloak.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-langfuse:
	$(MAKE) preflight WORKFLOW=converge-langfuse
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/langfuse.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-api-gateway:
	$(MAKE) preflight WORKFLOW=converge-api-gateway
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/api-gateway.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump $(ANSIBLE_TRACE_ARGS)

converge-gitea:
	$(MAKE) preflight WORKFLOW=converge-gitea
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/gitea.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump $(ANSIBLE_TRACE_ARGS)

converge-control-plane-recovery:
	$(MAKE) preflight WORKFLOW=converge-control-plane-recovery
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/control-plane-recovery.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-netbox:
	$(MAKE) preflight WORKFLOW=converge-netbox
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/netbox.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-searxng:
	$(MAKE) preflight WORKFLOW=converge-searxng
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/searxng.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-ollama:
	$(MAKE) preflight WORKFLOW=converge-ollama
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/ollama.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-n8n:
	$(MAKE) preflight WORKFLOW=converge-n8n
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/n8n.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
converge-dozzle:
	$(MAKE) preflight WORKFLOW=converge-dozzle
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/dozzle.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-open-webui:
	$(MAKE) preflight WORKFLOW=converge-open-webui
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/open-webui.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-homepage:
	$(MAKE) preflight WORKFLOW=converge-homepage
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/homepage.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

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
	$(UPTIME_KUMA_PYTHON) $(REPO_ROOT)/scripts/uptime_kuma_tool.py $(ACTION) $(UPTIME_KUMA_ARGS)

uptime-robot-manage:
	$(MAKE) preflight WORKFLOW=uptime-robot-manage
	@test -n "$(ACTION)" || (echo "set ACTION=<ensure|list-monitors>"; exit 1)
	$(PYTHON3) $(REPO_ROOT)/scripts/uptime_robot_tool.py $(ACTION) $(UPTIME_ROBOT_ARGS)

portainer-manage:
	$(MAKE) preflight WORKFLOW=portainer-manage
	@test -n "$(ACTION)" || (echo "set ACTION=<whoami|list-containers|container-logs|restart-container>"; exit 1)
	uvx --from requests python $(REPO_ROOT)/scripts/portainer_tool.py $(ACTION) $(PORTAINER_ARGS)

semaphore-manage:
	$(MAKE) preflight WORKFLOW=semaphore-manage
	@test -n "$(ACTION)" || (echo "set ACTION=<whoami|list-projects|list-templates|run-template|task-output>"; exit 1)
	$(PYTHON3) $(REPO_ROOT)/scripts/semaphore_tool.py $(ACTION) $(SEMAPHORE_ARGS)

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

database-dns:
	$(MAKE) preflight WORKFLOW=database-dns
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	$(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/database-dns.yml --env $(env) --

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
	python3 $(REPO_ROOT)/scripts/promotion_pipeline.py --promote --service "$(SERVICE)" --staging-receipt "$(STAGING_RECEIPT)" --requester-class "$(REQUESTER_CLASS)" --approver-classes "$(APPROVER_CLASSES)" $(if $(BRANCH),--branch "$(BRANCH)",) $(if $(EXTRA_ARGS),--extra-args "$(EXTRA_ARGS)",) $(if $(filter true,$(DRY_RUN)),--dry-run,)

live-apply-group:
	@test -n "$(group)" || (echo "set group=<group-id>"; exit 1)
	$(MAKE) check-canonical-truth
	uvx --from pyyaml python $(REPO_ROOT)/scripts/interface_contracts.py --check-live-apply "group:$(group)"
	@if [ "$(env)" = "production" ] && printf '%s' "$(EXTRA_ARGS)" | grep -Eq '(^|[[:space:]])bypass_promotion=true([[:space:]]|$$)'; then \
		python3 $(REPO_ROOT)/scripts/promotion_pipeline.py --emit-bypass-event --service "group:$(group)" --actor-id "$${USER:-unknown}" --correlation-id "break-glass:group:$(group):$$(date -u +%Y%m%dT%H%M%SZ)"; \
	fi
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/service_redundancy.py --check-live-apply
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/groups/$(group).yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump $(ANSIBLE_TRACE_ARGS) $(EXTRA_ARGS)

live-apply-service:
	@test -n "$(service)" || (echo "set service=<service-id>"; exit 1)
	$(MAKE) check-canonical-truth
	uvx --from pyyaml python $(REPO_ROOT)/scripts/interface_contracts.py --check-live-apply "service:$(service)"
	@if [ "$(env)" = "production" ] && printf '%s' "$(EXTRA_ARGS)" | grep -Eq '(^|[[:space:]])bypass_promotion=true([[:space:]]|$$)'; then \
		python3 $(REPO_ROOT)/scripts/promotion_pipeline.py --emit-bypass-event --service "$(service)" --actor-id "$${USER:-unknown}" --correlation-id "break-glass:service:$(service):$$(date -u +%Y%m%dT%H%M%SZ)"; \
	fi
	uv run --with pyyaml python $(REPO_ROOT)/scripts/standby_capacity.py --service "$(service)"
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/service_redundancy.py --check-live-apply --service "$(service)"
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/immutable_guest_replacement.py --check-live-apply --service "$(service)" $(if $(filter true,$(ALLOW_IN_PLACE_MUTATION)),--allow-in-place-mutation,)
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/services/$(service).yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump $(ANSIBLE_TRACE_ARGS) $(EXTRA_ARGS)

live-apply-site:
	$(MAKE) check-canonical-truth
	uvx --from pyyaml python $(REPO_ROOT)/scripts/interface_contracts.py --check-live-apply "site:site"
	@if [ "$(env)" = "production" ] && printf '%s' "$(EXTRA_ARGS)" | grep -Eq '(^|[[:space:]])bypass_promotion=true([[:space:]]|$$)'; then \
		python3 $(REPO_ROOT)/scripts/promotion_pipeline.py --emit-bypass-event --service "site" --actor-id "$${USER:-unknown}" --correlation-id "break-glass:site:$$(date -u +%Y%m%dT%H%M%SZ)"; \
	fi
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/service_redundancy.py --check-live-apply
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) $(ANSIBLE_SCOPED_RUN) --playbook $(REPO_ROOT)/playbooks/site.yml --env $(env) -- --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump $(ANSIBLE_TRACE_ARGS) $(EXTRA_ARGS)

live-apply-waves:
	@test -n "$(manifest)" || (echo "set manifest=config/dependency-waves/<plan>.yaml"; exit 1)
	uv run --with pyyaml python $(REPO_ROOT)/scripts/dependency_wave_apply.py --manifest "$(manifest)" --env "$(or $(env),production)" $(if $(CATALOG),--catalog "$(CATALOG)",) $(if $(EXTRA_ARGS),--extra-args "$(EXTRA_ARGS)",) $(WAVE_ARGS)

live-apply-train-status:
	python3 $(REPO_ROOT)/scripts/live_apply_merge_train.py --repo-root $(REPO_ROOT) status

live-apply-train-queue:
	@test -n "$(WORKSTREAMS)" || (echo 'set WORKSTREAMS="id-a id-b"'; exit 1)
	python3 $(REPO_ROOT)/scripts/live_apply_merge_train.py --repo-root $(REPO_ROOT) queue $(foreach ws,$(WORKSTREAMS),--workstream "$(ws)") --requested-by "$${USER:-unknown}"

live-apply-train-plan:
	python3 $(REPO_ROOT)/scripts/live_apply_merge_train.py --repo-root $(REPO_ROOT) plan $(foreach ws,$(WORKSTREAMS),--workstream "$(ws)")

live-apply-train-bundle:
	python3 $(REPO_ROOT)/scripts/live_apply_merge_train.py --repo-root $(REPO_ROOT) bundle $(foreach ws,$(WORKSTREAMS),--workstream "$(ws)")

live-apply-train-run:
	python3 $(REPO_ROOT)/scripts/live_apply_merge_train.py --repo-root $(REPO_ROOT) run $(foreach ws,$(WORKSTREAMS),--workstream "$(ws)") --requested-by "$${USER:-unknown}" $(if $(filter true,$(NO_AUTO_ROLLBACK)),--no-auto-rollback,)

live-apply-train-rollback:
	@test -n "$(BUNDLE)" || (echo "set BUNDLE=receipts/rollback-bundles/<bundle>.json"; exit 1)
	python3 $(REPO_ROOT)/scripts/live_apply_merge_train.py --repo-root $(REPO_ROOT) rollback --bundle "$(BUNDLE)"

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
