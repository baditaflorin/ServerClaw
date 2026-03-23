proxmox_api_url                 = "https://proxmox.lv3.org:8006/api2/json"
proxmox_api_token_id            = "lv3-automation@pve!primary"
proxmox_api_token_secret        = "set-at-runtime"
proxmox_node                    = "proxmox_florin"
proxmox_resource_pool           = "lv3"
proxmox_storage_pool            = "local"
proxmox_cloud_init_storage_pool = "local"
proxmox_network_bridge          = "vmbr10"
proxmox_insecure_skip_tls_verify = false

build_ssh_username         = "ops"
build_ssh_timeout          = "20m"
apt_proxy_url              = ""

debian_base_name      = "lv3-debian-base"
