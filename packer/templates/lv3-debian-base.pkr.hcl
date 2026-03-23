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

variable "bootstrap_clone_source" {
  type = string
}

variable "guest_nameserver" {
  type = string
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

variable "debian_base_vmid" {
  type = number
}

variable "debian_base_name" {
  type = string
}

source "proxmox-clone" "lv3_debian_base" {
  clone_vm                 = var.bootstrap_clone_source
  proxmox_url              = var.proxmox_api_url
  username                 = var.proxmox_api_token_id
  token                    = var.proxmox_api_token_secret
  node                     = var.proxmox_node
  pool                     = var.proxmox_resource_pool
  vm_id                    = var.debian_base_vmid
  vm_name                  = var.debian_base_name
  template_name            = var.debian_base_name
  template_description     = "LV3 Debian 13 base template built by Packer"
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
  nameserver               = var.guest_nameserver
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
    disk_size    = "16G"
    format       = "qcow2"
  }
}

build {
  sources = ["source.proxmox-clone.lv3_debian_base"]

  provisioner "shell" {
    environment_vars = [
      "APT_PROXY_URL=${var.apt_proxy_url}",
    ]
    scripts = [
      "${path.root}/../scripts/base-hardening.sh",
      "${path.root}/../scripts/step-cli-install.sh",
    ]
  }
}
