packer {
  required_plugins {
    proxmox = {
      source  = "github.com/hashicorp/proxmox"
      version = ">= 1.2.2"
    }
  }
}

variable "proxmox_api_url" {
  type = string
}

variable "proxmox_api_token_id" {
  type = string
}

variable "proxmox_api_token_secret" {
  type      = string
  sensitive = true
}

variable "proxmox_node" {
  type = string
}

variable "proxmox_storage_pool" {
  type = string
}

variable "proxmox_resource_pool" {
  type = string
}

variable "proxmox_cloud_init_storage_pool" {
  type = string
}

variable "proxmox_network_bridge" {
  type = string
}

variable "proxmox_insecure_skip_tls_verify" {
  type = bool
}

variable "build_ssh_username" {
  type = string
}

variable "build_ssh_timeout" {
  type = string
}

variable "apt_proxy_url" {
  type = string
}

variable "ops_base_vmid" {
  type = number
}

variable "ops_base_name" {
  type = string
}

variable "debian_base_name" {
  type = string
}

source "proxmox-clone" "lv3_ops_base" {
  clone_vm                 = var.debian_base_name
  proxmox_url              = var.proxmox_api_url
  username                 = var.proxmox_api_token_id
  token                    = var.proxmox_api_token_secret
  node                     = var.proxmox_node
  pool                     = var.proxmox_resource_pool
  vm_id                    = var.ops_base_vmid
  vm_name                  = var.ops_base_name
  template_name            = var.ops_base_name
  template_description     = "LV3 operator access template layered on lv3-debian-base"
  insecure_skip_tls_verify = var.proxmox_insecure_skip_tls_verify
  os                       = "l26"
  cores                    = 2
  sockets                  = 1
  memory                   = 2048
  qemu_agent               = true
  scsi_controller          = "virtio-scsi-single"
  cloud_init               = true
  cloud_init_storage_pool  = var.proxmox_cloud_init_storage_pool
  cloud_init_disk_type     = "ide"
  ssh_username             = var.build_ssh_username
  ssh_timeout              = var.build_ssh_timeout
  full_clone               = true

  network_adapters {
    bridge = var.proxmox_network_bridge
    model  = "virtio"
  }

  disks {
    type         = "scsi"
    storage_pool = var.proxmox_storage_pool
    disk_size    = "24G"
    format       = "qcow2"
  }
}

build {
  sources = ["source.proxmox-clone.lv3_ops_base"]
}
