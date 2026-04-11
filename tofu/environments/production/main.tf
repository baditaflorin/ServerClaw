provider "proxmox" {
  endpoint  = var.proxmox_endpoint
  api_token = var.proxmox_api_token
  insecure  = true
}

locals {
  bootstrap_authorized_key = trimspace(file("${path.root}/../../../keys/hetzner_llm_agents_ed25519.pub"))
}

module "nginx_lv3" {
  source = "../../modules/proxmox-vm"

  name                  = "nginx"
  description           = "nginx VM for lv3.org platform"
  node_name             = var.node_name
  vm_id                 = 110
  template_node_name    = var.template_node_name
  template_vmid         = var.template_vmid
  datastore_id            = var.datastore_id
  cloud_init_datastore_id = var.cloud_init_datastore_id
  cores                 = 2
  memory_mb             = 4096
  disk_gb               = 32
  bridge                = var.bridge
  mac_address           = "BC:24:11:0D:03:BB"
  ip_address            = "10.10.10.10"
  ip_cidr               = 24
  gateway               = "10.10.10.1"
  nameserver            = var.nameserver
  search_domain         = var.search_domain
  tags                  = ["ingress", "lv3", "nginx"]
  ci_user               = var.ci_user
  ssh_authorized_keys   = [local.bootstrap_authorized_key]
  user_data_file_id     = "local:snippets/nginx-user-data.yml"
}

module "docker_runtime_lv3" {
  source = "../../modules/proxmox-vm"

  name                    = "docker-runtime"
  description             = "docker-runtime VM for lv3.org platform"
  node_name               = var.node_name
  vm_id                   = 120
  template_node_name      = var.template_node_name
  template_vmid           = var.template_vmid
  datastore_id            = var.datastore_id
  cloud_init_datastore_id = var.cloud_init_datastore_id
  cores                   = 4
  memory_mb               = 24576
  disk_gb                 = 96
  bridge                  = var.bridge
  mac_address             = "BC:24:11:AA:99:7C"
  ip_address              = "10.10.10.20"
  ip_cidr                 = 24
  gateway                 = "10.10.10.1"
  nameserver              = var.nameserver
  search_domain           = var.search_domain
  tags                    = ["docker", "lv3", "runtime"]
  ci_user                 = var.ci_user
  ssh_authorized_keys     = [local.bootstrap_authorized_key]
  user_data_file_id       = "local:snippets/docker-runtime-user-data.yml"
}

module "docker_build_lv3" {
  source = "../../modules/proxmox-vm"

  name                    = "docker-build"
  description             = "docker-build VM for lv3.org platform"
  node_name               = var.node_name
  vm_id                   = 130
  template_node_name      = var.template_node_name
  template_vmid           = var.template_vmid
  datastore_id            = var.datastore_id
  cloud_init_datastore_id = var.cloud_init_datastore_id
  cores                   = 12
  memory_mb               = 24576
  disk_gb                 = 160
  bridge                  = var.bridge
  mac_address             = "BC:24:11:0F:8A:F2"
  ip_address              = "10.10.10.30"
  ip_cidr                 = 24
  gateway                 = "10.10.10.1"
  nameserver              = var.nameserver
  search_domain           = var.search_domain
  tags                    = ["build", "docker", "lv3"]
  ci_user                 = var.ci_user
  ssh_authorized_keys     = [local.bootstrap_authorized_key]
  user_data_file_id       = "local:snippets/docker-build-user-data.yml"
}

module "monitoring_lv3" {
  source = "../../modules/proxmox-vm"

  name                    = "monitoring"
  description             = "monitoring VM for lv3.org platform"
  node_name               = var.node_name
  vm_id                   = 140
  template_node_name      = var.template_node_name
  template_vmid           = var.template_vmid
  datastore_id            = var.datastore_id
  cloud_init_datastore_id = var.cloud_init_datastore_id
  cores                   = 4
  memory_mb               = 8192
  disk_gb                 = 64
  bridge                  = var.bridge
  mac_address             = "BC:24:11:B1:76:A0"
  ip_address              = "10.10.10.40"
  ip_cidr                 = 24
  gateway                 = "10.10.10.1"
  nameserver              = var.nameserver
  search_domain           = var.search_domain
  tags                    = ["grafana", "lv3", "monitoring"]
  ci_user                 = var.ci_user
  ssh_authorized_keys     = [local.bootstrap_authorized_key]
  user_data_file_id       = "local:snippets/monitoring-user-data.yml"
}

module "postgres_lv3" {
  source = "../../modules/proxmox-vm"

  name                    = "postgres"
  description             = "postgres VM for lv3.org platform"
  node_name               = var.node_name
  vm_id                   = 150
  template_node_name      = var.template_node_name
  template_vmid           = var.template_vmid
  datastore_id            = var.datastore_id
  cloud_init_datastore_id = var.cloud_init_datastore_id
  cores                   = 4
  memory_mb               = 8192
  disk_gb                 = 96
  bridge                  = var.bridge
  mac_address             = "BC:24:11:2A:2E:CA"
  ip_address              = "10.10.10.50"
  ip_cidr                 = 24
  gateway                 = "10.10.10.1"
  nameserver              = var.nameserver
  search_domain           = var.search_domain
  tags                    = ["database", "lv3", "postgres"]
  ci_user                 = var.ci_user
  ssh_authorized_keys     = [local.bootstrap_authorized_key]
  user_data_file_id       = "local:snippets/postgres-user-data.yml"
}

module "postgres_replica_lv3" {
  source = "../../modules/proxmox-vm"

  name                    = "postgres-replica"
  description             = "postgres replica VM for lv3.org platform"
  node_name               = var.node_name
  vm_id                   = 151
  template_node_name      = var.template_node_name
  template_vmid           = var.template_vmid
  datastore_id            = var.datastore_id
  cloud_init_datastore_id = var.cloud_init_datastore_id
  cores                   = 4
  memory_mb               = 8192
  disk_gb                 = 96
  bridge                  = var.bridge
  mac_address             = "BC:24:11:8C:51:17"
  ip_address              = "10.10.10.51"
  ip_cidr                 = 24
  gateway                 = "10.10.10.1"
  nameserver              = var.nameserver
  search_domain           = var.search_domain
  tags                    = ["database", "ha", "lv3", "postgres"]
  ci_user                 = var.ci_user
  ssh_authorized_keys     = [local.bootstrap_authorized_key]
  user_data_file_id       = "local:snippets/postgres-replica-user-data.yml"
}

module "backup_lv3" {
  source = "../../modules/proxmox-vm"

  name                    = "backup"
  description             = "backup VM for lv3.org platform"
  node_name               = var.node_name
  vm_id                   = 160
  template_node_name      = var.template_node_name
  template_vmid           = var.template_vmid
  datastore_id            = var.datastore_id
  cloud_init_datastore_id = var.cloud_init_datastore_id
  cores                   = 4
  memory_mb               = 8192
  disk_gb                 = 32
  bridge                  = var.bridge
  mac_address             = "BC:24:11:2D:5F:37"
  ip_address              = "10.10.10.60"
  ip_cidr                 = 24
  gateway                 = "10.10.10.1"
  nameserver              = var.nameserver
  search_domain           = var.search_domain
  tags                    = ["backup", "lv3", "pbs"]
  ci_user                 = var.ci_user
  ssh_authorized_keys     = [local.bootstrap_authorized_key]
  user_data_file_id       = "local:snippets/backup-user-data.yml"
  extra_disks = [
    {
      interface    = "scsi1"
      datastore_id = "local"
      size_gb      = 640
    }
  ]
}
