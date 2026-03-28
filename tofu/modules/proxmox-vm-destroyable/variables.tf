variable "name" {
  type = string
}

variable "description" {
  type = string
}

variable "node_name" {
  type = string
}

variable "vm_id" {
  type = number
}

variable "template_node_name" {
  type = string
}

variable "template_vmid" {
  type = number
}

variable "datastore_id" {
  type = string
}

variable "cloud_init_datastore_id" {
  type = string
}

variable "cores" {
  type = number
}

variable "sockets" {
  type    = number
  default = 1
}

variable "cpu_type" {
  type    = string
  default = "host"
}

variable "memory_mb" {
  type = number
}

variable "disk_gb" {
  type = number
}

variable "bridge" {
  type = string
}

variable "mac_address" {
  type = string
}

variable "ip_address" {
  type = string
}

variable "ip_cidr" {
  type = number
}

variable "gateway" {
  type = string
}

variable "nameserver" {
  type = string
}

variable "search_domain" {
  type = string
}

variable "tags" {
  type = list(string)
}

variable "startup_order" {
  type    = number
  default = null
}

variable "on_boot" {
  type    = bool
  default = true
}

variable "started" {
  type    = bool
  default = true
}

variable "protection" {
  type    = bool
  default = false
}

variable "reboot_after_update" {
  type    = bool
  default = true
}

variable "scsi_hardware" {
  type    = string
  default = "virtio-scsi-single"
}

variable "ci_user" {
  type = string
}

variable "ssh_authorized_keys" {
  type = list(string)
}

variable "user_data_file_id" {
  type    = string
  default = null
}

variable "agent_enabled" {
  type    = bool
  default = false
}

variable "agent_timeout" {
  type    = string
  default = "15m"
}

variable "network_firewall" {
  type    = bool
  default = true
}

variable "extra_disks" {
  type = list(object({
    interface    = string
    datastore_id = string
    size_gb      = number
  }))
  default = []
}
