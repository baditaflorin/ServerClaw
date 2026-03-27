variable "fixture_id" {
  type = string
}

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

variable "vmid_range" {
  type = list(number)
}

variable "lifetime_minutes" {
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

variable "ci_user" {
  type = string
}

variable "ssh_authorized_keys" {
  type = list(string)
}
