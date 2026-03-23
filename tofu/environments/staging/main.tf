provider "proxmox" {
  endpoint  = var.proxmox_endpoint
  api_token = var.proxmox_api_token
  insecure  = true
}

locals {
  bootstrap_authorized_key = trimspace(file("${path.root}/../../../keys/hetzner_llm_agents_ed25519.pub"))
}

module "docker_runtime_staging_lv3" {
  source = "../../modules/proxmox-vm"

  name                    = "docker-runtime-staging-lv3"
  description             = "docker-runtime staging VM for lv3.org platform"
  node_name               = var.node_name
  vm_id                   = 220
  template_node_name      = var.template_node_name
  template_vmid           = var.template_vmid
  datastore_id            = var.datastore_id
  cloud_init_datastore_id = var.cloud_init_datastore_id
  cores                   = 2
  memory_mb               = 8192
  disk_gb                 = 64
  bridge                  = var.bridge
  mac_address             = "BC:24:11:20:00:20"
  ip_address              = "10.20.10.20"
  ip_cidr                 = 24
  gateway                 = "10.20.10.1"
  nameserver              = var.nameserver
  search_domain           = var.search_domain
  tags                    = ["docker", "runtime", "staging", "lv3"]
  startup_order           = 20
  ci_user                 = var.ci_user
  ssh_authorized_keys     = [local.bootstrap_authorized_key]
}

module "monitoring_staging_lv3" {
  source = "../../modules/proxmox-vm"

  name                    = "monitoring-staging-lv3"
  description             = "monitoring staging VM for lv3.org platform"
  node_name               = var.node_name
  vm_id                   = 240
  template_node_name      = var.template_node_name
  template_vmid           = var.template_vmid
  datastore_id            = var.datastore_id
  cloud_init_datastore_id = var.cloud_init_datastore_id
  cores                   = 2
  memory_mb               = 4096
  disk_gb                 = 48
  bridge                  = var.bridge
  mac_address             = "BC:24:11:20:00:40"
  ip_address              = "10.20.10.40"
  ip_cidr                 = 24
  gateway                 = "10.20.10.1"
  nameserver              = var.nameserver
  search_domain           = var.search_domain
  tags                    = ["monitoring", "staging", "lv3"]
  startup_order           = 21
  ci_user                 = var.ci_user
  ssh_authorized_keys     = [local.bootstrap_authorized_key]
}
