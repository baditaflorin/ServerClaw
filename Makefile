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
SURFACE ?=
HOST ?= proxmox_florin
TOOL ?=
IMAGE_ID ?=
IMAGE_TAG ?=
WRITE ?= false
APPLY ?= false
EXCEPTION_REASON ?=
EXCEPTION_OWNER ?=
EXCEPTION_REVIEW_BY ?=
SECRET_ID ?=
ROTATION_ARGS ?=

.PHONY: validate validate-generated-vars validate-ansible-syntax validate-yaml validate-role-argument-specs validate-ansible-lint validate-shell validate-json validate-data-models validate-health-probes generate-platform-vars show-platform-facts generate-status-docs generate-status generate-ops-portal deploy-ops-portal validate-generated-docs validate-generated-portals receipts receipt-info workflows workflow-info commands command-info show-service lanes lane-info api-publication api-publication-info agent-tools agent-tool-info export-mcp-tools check-image-freshness upgrade-container-image preflight syntax-check syntax-check-monitoring syntax-check-ntopng syntax-check-guest-network-policy syntax-check-docker-runtime syntax-check-backup-vm syntax-check-control-plane-recovery syntax-check-uptime-kuma syntax-check-mail-platform syntax-check-openbao syntax-check-step-ca syntax-check-windmill syntax-check-keycloak syntax-check-netbox syntax-check-open-webui syntax-check-mattermost syntax-check-portainer syntax-check-rag-context syntax-check-secret-rotation check-platform-drift install-proxmox configure-network configure-ingress configure-edge-publication configure-tailscale provision-guests harden-access harden-guest-access harden-security provision-api-access converge-guest-network-policy converge-monitoring converge-ntopng converge-docker-runtime converge-postgres-vm converge-mail-platform converge-openbao converge-step-ca converge-windmill converge-control-plane-recovery converge-keycloak converge-netbox converge-open-webui converge-mattermost converge-portainer converge-rag-context rotate-secret deploy-uptime-kuma uptime-kuma-manage portainer-manage configure-backups configure-backup-vm database-dns start-workstream

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

validate-data-models:
	$(REPO_ROOT)/scripts/validate_repo.sh data-models

generate-platform-vars:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/generate_platform_vars.py --write

show-platform-facts:
	uvx --from ansible-core ansible-inventory -i $(ANSIBLE_INVENTORY) --host $(HOST) --yaml

validate-health-probes:
	$(REPO_ROOT)/scripts/validate_repo.sh health-probes

check-image-freshness:
	$(REPO_ROOT)/scripts/container_image_policy.py --check-freshness

upgrade-container-image:
	@test -n "$(IMAGE_ID)" || (echo "set IMAGE_ID=<image-id>"; exit 1)
	$(REPO_ROOT)/scripts/upgrade_container_image.py --image-id "$(IMAGE_ID)" $(if $(IMAGE_TAG),--tag "$(IMAGE_TAG)",) $(if $(filter true,$(WRITE)),--write,) $(if $(filter true,$(APPLY)),--apply,) $(if $(EXCEPTION_REASON),--exception-reason "$(EXCEPTION_REASON)",) $(if $(EXCEPTION_OWNER),--exception-owner "$(EXCEPTION_OWNER)",) $(if $(EXCEPTION_REVIEW_BY),--exception-review-by "$(EXCEPTION_REVIEW_BY)",)

generate-status-docs:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/generate_status_docs.py --write

generate-ops-portal:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/generate_ops_portal.py --write

deploy-ops-portal: generate-ops-portal
	$(MAKE) configure-edge-publication

generate-status: generate-status-docs generate-ops-portal

validate-generated-docs:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/generate_status_docs.py --check

validate-generated-portals:
	uvx --from pyyaml python $(REPO_ROOT)/scripts/generate_ops_portal.py --check

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

show-service:
	@test -n "$(SERVICE)" || (echo "set SERVICE=<service-id>"; exit 1)
	uvx --from pyyaml python $(REPO_ROOT)/scripts/service_catalog.py --service $(SERVICE)

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
	uvx --from pyyaml python $(REPO_ROOT)/scripts/platform_observation_tool.py

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
	ANSIBLE_HOST_KEY_CHECKING=False $(ANSIBLE_ENV) ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/public-edge.yml --private-key $(BOOTSTRAP_KEY) -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

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
	@test -n "$(ACTION)" || (echo "set ACTION=<bootstrap|ensure-monitors|list-monitors>"; exit 1)
	$(UPTIME_KUMA_PYTHON) $(REPO_ROOT)/scripts/uptime_kuma_tool.py $(ACTION) $(UPTIME_KUMA_ARGS)

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

start-workstream:
	@test -n "$(WORKSTREAM)" || (echo "set WORKSTREAM=<workstream-id>"; exit 1)
	$(REPO_ROOT)/scripts/create-workstream.sh $(WORKSTREAM)
