REPO_ROOT := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
ANSIBLE_INVENTORY := $(REPO_ROOT)/inventory/hosts.yml
BOOTSTRAP_KEY ?= /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519
ANSIBLE_LOCAL_TEMP ?= /tmp/proxmox_florin_server-ansible-local
ANSIBLE_REMOTE_TEMP ?= /tmp
ANSIBLE_ENV := ANSIBLE_LOCAL_TEMP=$(ANSIBLE_LOCAL_TEMP) ANSIBLE_REMOTE_TEMP=$(ANSIBLE_REMOTE_TEMP)
UPTIME_KUMA_PYTHON ?= $(REPO_ROOT)/.local/uptime-kuma/client-venv/bin/python
ACTION ?= list-monitors
UPTIME_KUMA_ARGS ?=
PORTAINER_ARGS ?=
RECEIPT ?=
COMMAND ?=
SERVICE ?=
DURATION_MINUTES ?= 30
REASON ?=
FORCE ?= false
WARNING_DAYS ?= 45
INACTIVE_DAYS ?= 60
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

.PHONY: validate validate-generated-vars validate-ansible-syntax validate-yaml validate-role-argument-specs validate-ansible-lint validate-shell validate-json validate-compose-runtime-envs validate-data-models validate-health-probes validate-tofu generate-platform-vars show-platform-facts generate-slo-rules validate-generated-slo generate-status-docs generate-status generate-ops-portal generate-changelog-portal docs deploy-ops-portal deploy-changelog-portal deploy-docs-portal validate-generated-docs validate-generated-portals receipts receipt-info workflows workflow-info commands command-info services show-service environments environment-info lanes lane-info api-publication api-publication-info agent-tools agent-tool-info export-mcp-tools check-image-freshness upgrade-container-image pin-image scaffold-service install-hooks pre-push-gate gate-status dr-status dr-runbook post-merge-gate integration-tests nightly-integration-tests setup preflight syntax-check syntax-check-monitoring syntax-check-ntopng syntax-check-guest-network-policy syntax-check-docker-runtime syntax-check-backup-vm syntax-check-control-plane-recovery syntax-check-uptime-kuma syntax-check-mail-platform syntax-check-openbao syntax-check-step-ca syntax-check-windmill syntax-check-keycloak syntax-check-netbox syntax-check-open-webui syntax-check-mattermost syntax-check-portainer syntax-check-rag-context syntax-check-secret-rotation collection-sync collection-build collection-publish collection-install check-platform-drift drift-report open-maintenance-window close-maintenance-window operator-onboard operator-offboard sync-operators quarterly-access-review install-proxmox configure-network configure-ingress configure-edge-publication configure-tailscale provision-guests harden-access harden-guest-access harden-security provision-api-access converge-guest-network-policy converge-monitoring converge-ntopng converge-docker-runtime converge-postgres-vm converge-mail-platform converge-openbao converge-step-ca converge-windmill converge-control-plane-recovery converge-keycloak converge-netbox converge-open-webui converge-mattermost converge-portainer converge-rag-context rotate-secret deploy-uptime-kuma uptime-kuma-manage uptime-robot-manage portainer-manage configure-backups configure-backup-vm database-dns provision-subdomain start-workstream promote live-apply-group live-apply-service live-apply-site build-check-runners push-check-runners run-checks warm-cache cache-status fixture-up fixture-down fixture-list fixture-reaper install-cli update-cli validate-packer remote-packer-validate packer-template-rebuild remote-tofu-plan remote-tofu-apply tofu-drift tofu-import

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

validate-shell:
	$(REPO_ROOT)/scripts/validate_repo.sh shell

validate-json:
	$(REPO_ROOT)/scripts/validate_repo.sh json

validate-compose-runtime-envs:
	$(REPO_ROOT)/scripts/validate_repo.sh compose-runtime-envs

validate-data-models:
	$(REPO_ROOT)/scripts/validate_repo.sh data-models

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

post-merge-gate:
	python3 $(REPO_ROOT)/config/windmill/scripts/post-merge-gate.py --repo-path $(REPO_ROOT)

integration-tests:
	uv run --with-requirements $(REPO_ROOT)/requirements/integration-tests.txt python $(REPO_ROOT)/scripts/integration_suite.py

nightly-integration-tests:
	python3 $(REPO_ROOT)/config/windmill/scripts/nightly-integration-tests.py --repo-path $(REPO_ROOT)

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

show-platform-facts:
	uvx --from ansible-core ansible-inventory -i $(ANSIBLE_INVENTORY) --host $(HOST) --yaml

validate-health-probes:
	$(REPO_ROOT)/scripts/validate_repo.sh health-probes

validate-tofu:
	$(REPO_ROOT)/scripts/tofu_exec.sh validate all

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

generate-ops-portal:
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/generate_ops_portal.py --write

generate-changelog-portal:
	uv run --with pyyaml --with jsonschema python $(REPO_ROOT)/scripts/generate_changelog_portal.py --write

docs:
	uv run --with-requirements $(REPO_ROOT)/requirements/docs.txt python $(REPO_ROOT)/scripts/generate_docs_site.py --write
	uv run --with-requirements $(REPO_ROOT)/requirements/docs.txt mkdocs build --strict --config-file $(REPO_ROOT)/mkdocs.yml --site-dir $(REPO_ROOT)/build/docs-portal

deploy-ops-portal: generate-ops-portal
	$(MAKE) configure-edge-publication

deploy-changelog-portal: generate-changelog-portal
	$(MAKE) configure-edge-publication

deploy-docs-portal: docs
	$(MAKE) configure-edge-publication

generate-status: generate-slo-rules generate-status-docs generate-ops-portal generate-changelog-portal docs

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
	$(REPO_ROOT)/scripts/workflow_catalog.py --list

workflow-info:
	@test -n "$(WORKFLOW)" || (echo "set WORKFLOW=<workflow-id>"; exit 1)
	$(REPO_ROOT)/scripts/workflow_catalog.py --workflow $(WORKFLOW)

commands:
	$(REPO_ROOT)/scripts/command_catalog.py --list

command-info:
	@test -n "$(COMMAND)" || (echo "set COMMAND=<command-id>"; exit 1)
	$(REPO_ROOT)/scripts/command_catalog.py --command $(COMMAND)

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
		$(REPO_ROOT)/scripts/preflight_controller_local.py --list; \
		echo "set WORKFLOW=<workflow-id>"; \
		exit 0; \
	else \
		$(REPO_ROOT)/scripts/preflight_controller_local.py --workflow $(WORKFLOW); \
	fi

syntax-check:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --syntax-check

syntax-check-monitoring:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/monitoring-stack.yml --syntax-check

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

syntax-check-windmill:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/windmill.yml --syntax-check

syntax-check-keycloak:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/keycloak.yml --syntax-check

syntax-check-netbox:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/netbox.yml --syntax-check

syntax-check-open-webui:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/open-webui.yml --syntax-check

syntax-check-portainer:
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/portainer.yml --syntax-check

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

open-maintenance-window:
	$(MAKE) preflight WORKFLOW=open-maintenance-window
	@test -n "$(SERVICE)" || (echo "set SERVICE=<service-id>"; exit 1)
	@test -n "$(REASON)" || (echo "set REASON=<planned-change-reason>"; exit 1)
	uv run --with pyyaml --with nats-py python $(REPO_ROOT)/scripts/maintenance_window_tool.py open --service "$(SERVICE)" --reason "$(REASON)" --duration-minutes $(DURATION_MINUTES)

close-maintenance-window:
	$(MAKE) preflight WORKFLOW=close-maintenance-window
	@test -n "$(SERVICE)" || (echo "set SERVICE=<service-id|all>"; exit 1)
	uv run --with pyyaml --with nats-py python $(REPO_ROOT)/scripts/maintenance_window_tool.py close --service "$(SERVICE)" $(if $(filter true,$(FORCE)),--force,)

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
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY)

configure-network:
	$(MAKE) preflight WORKFLOW=configure-network
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags repository,network

configure-ingress:
	$(MAKE) preflight WORKFLOW=configure-ingress
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags ingress

configure-edge-publication:
	$(MAKE) preflight WORKFLOW=configure-edge-publication
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/public-edge.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump $(EXTRA_ARGS)

configure-tailscale:
	$(MAKE) preflight WORKFLOW=configure-tailscale
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags tailscale

provision-guests:
	$(MAKE) preflight WORKFLOW=provision-guests
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags guests

harden-access:
	$(MAKE) preflight WORKFLOW=harden-access
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags access

harden-guest-access:
	$(MAKE) preflight WORKFLOW=harden-guest-access
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/guest-access.yml --private-key $(BOOTSTRAP_KEY)

harden-security:
	$(MAKE) preflight WORKFLOW=harden-security
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags security

provision-api-access:
	$(MAKE) preflight WORKFLOW=provision-api-access
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags api-access

converge-guest-network-policy:
	$(MAKE) preflight WORKFLOW=converge-guest-network-policy
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/guest-network-policy.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-monitoring:
	$(MAKE) preflight WORKFLOW=converge-monitoring
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/monitoring-stack.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-ntopng:
	$(MAKE) preflight WORKFLOW=converge-ntopng
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/ntopng.yml --private-key $(BOOTSTRAP_KEY)

converge-docker-runtime:
	$(MAKE) preflight WORKFLOW=converge-docker-runtime
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/docker-runtime.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-postgres-vm:
	$(MAKE) preflight WORKFLOW=converge-postgres-vm
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/postgres-vm.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-mail-platform:
	$(MAKE) preflight WORKFLOW=converge-mail-platform
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/mail-platform.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-openbao:
	$(MAKE) preflight WORKFLOW=converge-openbao
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/openbao.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-step-ca:
	$(MAKE) preflight WORKFLOW=converge-step-ca
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/step-ca.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-windmill:
	$(MAKE) preflight WORKFLOW=converge-windmill
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/windmill.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-keycloak:
	$(MAKE) preflight WORKFLOW=converge-keycloak
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/keycloak.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-control-plane-recovery:
	$(MAKE) preflight WORKFLOW=converge-control-plane-recovery
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/control-plane-recovery.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-netbox:
	$(MAKE) preflight WORKFLOW=converge-netbox
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/netbox.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-open-webui:
	$(MAKE) preflight WORKFLOW=converge-open-webui
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/open-webui.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-rag-context:
	$(MAKE) preflight WORKFLOW=converge-rag-context
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/rag-context.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-portainer:
	$(MAKE) preflight WORKFLOW=converge-portainer
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/portainer.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

converge-mattermost:
	$(MAKE) preflight WORKFLOW=converge-mattermost
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/mattermost.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

rotate-secret:
	$(MAKE) preflight WORKFLOW=rotate-secret
	@test -n "$(SECRET_ID)" || (echo "set SECRET_ID=<secret-id>"; exit 1)
	python3 $(REPO_ROOT)/scripts/secret_rotation.py --secret $(SECRET_ID) $(ROTATION_ARGS)

deploy-uptime-kuma:
	$(MAKE) preflight WORKFLOW=deploy-uptime-kuma
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/uptime-kuma.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

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

configure-backups:
	$(MAKE) preflight WORKFLOW=configure-backups
	PROXMOX_BACKUP_CIFS_SERVER=$${PROXMOX_BACKUP_CIFS_SERVER:?set PROXMOX_BACKUP_CIFS_SERVER} \
	PROXMOX_BACKUP_CIFS_SHARE=$${PROXMOX_BACKUP_CIFS_SHARE:?set PROXMOX_BACKUP_CIFS_SHARE} \
	PROXMOX_BACKUP_CIFS_USERNAME=$${PROXMOX_BACKUP_CIFS_USERNAME:?set PROXMOX_BACKUP_CIFS_USERNAME} \
	PROXMOX_BACKUP_CIFS_PASSWORD=$${PROXMOX_BACKUP_CIFS_PASSWORD:?set PROXMOX_BACKUP_CIFS_PASSWORD} \
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags storage,backups

configure-backup-vm:
	$(MAKE) preflight WORKFLOW=configure-backup-vm
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/backup-vm.yml --private-key $(BOOTSTRAP_KEY)

database-dns:
	$(MAKE) preflight WORKFLOW=database-dns
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} \
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/database-dns.yml

provision-subdomain:
	@test -n "$(FQDN)" || (echo "set FQDN=<hostname>"; exit 1)
	$(MAKE) preflight WORKFLOW=provision-subdomain
	uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_catalog.py --fqdn "$(FQDN)" --provision-check
	$(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/provision-subdomain.yml -e subdomain_fqdn="$(FQDN)" $(EXTRA_ARGS)
	@if [ "$$(uvx --from pyyaml python $(REPO_ROOT)/scripts/subdomain_catalog.py --fqdn "$(FQDN)" --print-field route_mode)" = "edge" ]; then \
		$(MAKE) configure-edge-publication EXTRA_ARGS="$(EXTRA_ARGS)"; \
	fi

start-workstream:
	@test -n "$(WORKSTREAM)" || (echo "set WORKSTREAM=<workstream-id>"; exit 1)
	$(REPO_ROOT)/scripts/create-workstream.sh $(WORKSTREAM)

promote:
	@test -n "$(SERVICE)" || (echo "set SERVICE=<service-id>"; exit 1)
	@test -n "$(STAGING_RECEIPT)" || (echo "set STAGING_RECEIPT=receipts/live-applies/staging/<receipt>.json"; exit 1)
	python3 $(REPO_ROOT)/scripts/promotion_pipeline.py --promote --service "$(SERVICE)" --staging-receipt "$(STAGING_RECEIPT)" --requester-class "$(REQUESTER_CLASS)" --approver-classes "$(APPROVER_CLASSES)" $(if $(BRANCH),--branch "$(BRANCH)",) $(if $(EXTRA_ARGS),--extra-args "$(EXTRA_ARGS)",) $(if $(filter true,$(DRY_RUN)),--dry-run,)

live-apply-group:
	@test -n "$(group)" || (echo "set group=<group-id>"; exit 1)
	@if [ "$(env)" = "production" ] && printf '%s' "$(EXTRA_ARGS)" | grep -Eq '(^|[[:space:]])bypass_promotion=true([[:space:]]|$$)'; then \
		python3 $(REPO_ROOT)/scripts/promotion_pipeline.py --emit-bypass-event --service "group:$(group)" --actor-id "$${USER:-unknown}" --correlation-id "break-glass:group:$(group):$$(date -u +%Y%m%dT%H%M%SZ)"; \
	fi
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/groups/$(group).yml --private-key $(BOOTSTRAP_KEY) -e env=$(env) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump $(EXTRA_ARGS)

live-apply-service:
	@test -n "$(service)" || (echo "set service=<service-id>"; exit 1)
	@if [ "$(env)" = "production" ] && printf '%s' "$(EXTRA_ARGS)" | grep -Eq '(^|[[:space:]])bypass_promotion=true([[:space:]]|$$)'; then \
		python3 $(REPO_ROOT)/scripts/promotion_pipeline.py --emit-bypass-event --service "$(service)" --actor-id "$${USER:-unknown}" --correlation-id "break-glass:service:$(service):$$(date -u +%Y%m%dT%H%M%SZ)"; \
	fi
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/services/$(service).yml --private-key $(BOOTSTRAP_KEY) -e env=$(env) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump $(EXTRA_ARGS)

live-apply-site:
	@if [ "$(env)" = "production" ] && printf '%s' "$(EXTRA_ARGS)" | grep -Eq '(^|[[:space:]])bypass_promotion=true([[:space:]]|$$)'; then \
		python3 $(REPO_ROOT)/scripts/promotion_pipeline.py --emit-bypass-event --service "site" --actor-id "$${USER:-unknown}" --correlation-id "break-glass:site:$$(date -u +%Y%m%dT%H%M%SZ)"; \
	fi
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) -e env=$(env) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump $(EXTRA_ARGS)

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
	SERVICE="$(SERVICE)" COMMAND="$(COMMAND)" $(REPO_ROOT)/scripts/remote_exec.sh remote-image-build --local-fallback

remote-exec:
	@test -n "$(COMMAND)" || (echo "set COMMAND=<shell-command>"; exit 1)
	COMMAND="$(COMMAND)" $(REPO_ROOT)/scripts/remote_exec.sh remote-exec --local-fallback

check-build-server:
	$(REPO_ROOT)/scripts/remote_exec.sh check-build-server

remote-tofu-plan:
	@test -n "$(ENV)" || (echo "set ENV=<production|staging>"; exit 1)
	@COMMAND="$$(python3 $(REPO_ROOT)/scripts/tofu_remote_command.py plan $(ENV))" \
		$(REPO_ROOT)/scripts/remote_exec.sh remote-exec

remote-tofu-apply:
	@test -n "$(ENV)" || (echo "set ENV=<production|staging>"; exit 1)
	@COMMAND="$$(python3 $(REPO_ROOT)/scripts/tofu_remote_command.py apply $(ENV))" \
		$(REPO_ROOT)/scripts/remote_exec.sh remote-exec

tofu-drift:
	@test -n "$(ENV)" || (echo "set ENV=<production|staging>"; exit 1)
	@COMMAND="$$(python3 $(REPO_ROOT)/scripts/tofu_remote_command.py drift $(ENV))" \
		$(REPO_ROOT)/scripts/remote_exec.sh remote-exec

tofu-import:
	@test -n "$(VM)" || (echo "set VM=<vm-name>"; exit 1)
	@test "$(ENV)" = "production" || (echo "tofu-import currently supports ENV=production"; exit 1)
	@COMMAND="$$(python3 $(REPO_ROOT)/scripts/tofu_remote_command.py import $(ENV) --vm $(VM))" \
		$(REPO_ROOT)/scripts/remote_exec.sh remote-exec
