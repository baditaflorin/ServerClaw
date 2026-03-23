terraform {
  required_version = ">= 1.10.0"

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "= 0.99.0"
    }
  }
}

variable "proxmox_endpoint" {
  type      = string
  sensitive = true
}

variable "proxmox_api_token" {
  type      = string
  sensitive = true
}

variable "node_name" {
  type = string
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

variable "bridge" {
  type = string
}

variable "nameserver" {
  type = string
}

variable "search_domain" {
  type = string
}

variable "ci_user" {
  type = string
}
