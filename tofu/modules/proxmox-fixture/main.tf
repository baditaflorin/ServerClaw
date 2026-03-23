module "fixture_vm" {
  source = "../proxmox-vm"

  name                    = var.name
  description             = "${var.description} | fixture=${var.fixture_id} | lifetime=${var.lifetime_minutes}m"
  node_name               = var.node_name
  vm_id                   = var.vm_id
  template_node_name      = var.template_node_name
  template_vmid           = var.template_vmid
  datastore_id            = var.datastore_id
  cloud_init_datastore_id = var.cloud_init_datastore_id
  cores                   = var.cores
  memory_mb               = var.memory_mb
  disk_gb                 = var.disk_gb
  bridge                  = var.bridge
  mac_address             = var.mac_address
  ip_address              = var.ip_address
  ip_cidr                 = var.ip_cidr
  gateway                 = var.gateway
  nameserver              = var.nameserver
  search_domain           = var.search_domain
  ci_user                 = var.ci_user
  ssh_authorized_keys     = var.ssh_authorized_keys
  tags                    = distinct(concat(var.tags, ["ephemeral", "fixture"]))
  protection              = false
  prevent_destroy         = false
}
