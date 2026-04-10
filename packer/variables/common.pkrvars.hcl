proxmox_api_url                 = "https://proxmox.example.com:8006/api2/json"  # <-- CHANGE to your Proxmox FQDN
proxmox_api_token_id            = "automation@pve!primary"                      # <-- CHANGE to your API token
proxmox_api_token_secret        = "set-at-runtime"
proxmox_node                    = "proxmox"                                     # <-- CHANGE to your Proxmox node name
proxmox_resource_pool           = "platform"                                    # <-- CHANGE to your pool name
proxmox_storage_pool            = "local"
proxmox_cloud_init_storage_pool = "local"
proxmox_network_bridge          = "vmbr10"
proxmox_insecure_skip_tls_verify = false

build_ssh_username         = "ops"
build_ssh_timeout          = "20m"
apt_proxy_url              = ""

debian_base_name      = "debian-base"
