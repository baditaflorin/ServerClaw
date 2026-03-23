terraform {
  required_providers {
    proxmox = {
      source = "bpg/proxmox"
    }
  }
}

resource "proxmox_virtual_environment_vm" "this" {
  name                = var.name
  description         = var.description
  node_name           = var.node_name
  vm_id               = var.vm_id
  tags                = var.tags
  on_boot             = var.on_boot
  started             = var.started
  protection          = var.protection
  reboot_after_update = var.reboot_after_update
  scsi_hardware       = var.scsi_hardware
  boot_order          = ["scsi0"]

  clone {
    node_name    = var.template_node_name
    vm_id        = var.template_vmid
    datastore_id = var.datastore_id
    full         = true
    retries      = 3
  }

  cpu {
    cores   = var.cores
    sockets = var.sockets
    type    = var.cpu_type
  }

  memory {
    dedicated = var.memory_mb
    floating  = 0
    shared    = 0
  }

  agent {
    enabled = true
    trim    = true
    timeout = "15m"
  }

  operating_system {
    type = "l26"
  }

  serial_device {
    device = "socket"
  }

  dynamic "startup" {
    for_each = var.startup_order == null ? [] : [var.startup_order]

    content {
      order = startup.value
    }
  }

  network_device = [
    {
      bridge       = var.bridge
      disconnected = false
      enabled      = true
      firewall     = var.network_firewall
      mac_address  = upper(var.mac_address)
      model        = "virtio"
      mtu          = 0
      queues       = 0
      rate_limit   = 0
      trunks       = ""
      vlan_id      = 0
    }
  ]

  initialization {
    datastore_id = var.cloud_init_datastore_id
    interface    = "ide2"

    dns {
      domain  = var.search_domain
      servers = [var.nameserver]
    }

    ip_config {
      ipv4 {
        address = "${var.ip_address}/${var.ip_cidr}"
        gateway = var.gateway
      }
    }

    dynamic "user_account" {
      for_each = var.user_data_file_id == null ? [1] : []

      content {
        username = var.ci_user
        keys     = var.ssh_authorized_keys
      }
    }

    user_data_file_id = var.user_data_file_id
  }

  disk {
    interface    = "scsi0"
    datastore_id = var.datastore_id
    size         = var.disk_gb
    backup       = true
    replicate    = true
    ssd          = false
    iothread     = false
    discard      = "ignore"
    file_format  = "qcow2"
  }

  dynamic "disk" {
    for_each = var.extra_disks

    content {
      interface    = disk.value.interface
      datastore_id = disk.value.datastore_id
      size         = disk.value.size_gb
      backup       = true
      replicate    = true
      file_format  = "raw"
    }
  }

  lifecycle {
    prevent_destroy = var.prevent_destroy
    ignore_changes  = [agent[0].type, clone, keyboard_layout, node_name]
  }
}
