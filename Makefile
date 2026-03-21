REPO_ROOT := $(realpath $(dir $(lastword $(MAKEFILE_LIST))))
ANSIBLE_INVENTORY := $(REPO_ROOT)/inventory/hosts.yml
BOOTSTRAP_KEY := $(REPO_ROOT)/.local/ssh/hetzner_llm_agents_ed25519

.PHONY: syntax-check install-proxmox configure-network configure-ingress provision-guests harden-access harden-guest-access harden-security provision-api-access configure-backups

syntax-check:
	ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --syntax-check

install-proxmox:
	ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY)

configure-network:
	ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags repository,network

configure-ingress:
	ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags ingress

provision-guests:
	ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags guests

harden-access:
	ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags access

harden-guest-access:
	ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/guest-access.yml --private-key $(BOOTSTRAP_KEY)

harden-security:
	HETZNER_DNS_API_TOKEN=$${HETZNER_DNS_API_TOKEN:?set HETZNER_DNS_API_TOKEN} ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags security

provision-api-access:
	ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags api-access

configure-backups:
	PROXMOX_BACKUP_CIFS_SERVER=$${PROXMOX_BACKUP_CIFS_SERVER:?set PROXMOX_BACKUP_CIFS_SERVER} \
	PROXMOX_BACKUP_CIFS_SHARE=$${PROXMOX_BACKUP_CIFS_SHARE:?set PROXMOX_BACKUP_CIFS_SHARE} \
	PROXMOX_BACKUP_CIFS_USERNAME=$${PROXMOX_BACKUP_CIFS_USERNAME:?set PROXMOX_BACKUP_CIFS_USERNAME} \
	PROXMOX_BACKUP_CIFS_PASSWORD=$${PROXMOX_BACKUP_CIFS_PASSWORD:?set PROXMOX_BACKUP_CIFS_PASSWORD} \
	ansible-playbook -i $(ANSIBLE_INVENTORY) $(REPO_ROOT)/playbooks/site.yml --private-key $(BOOTSTRAP_KEY) --tags storage,backups
