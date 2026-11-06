region     = "global"
datacenter = "dc1"
name       = "docker-build"
data_dir   = "/var/lib/nomad"
bind_addr  = "0.0.0.0"
log_level  = "INFO"

ports {
  http = 4646
  rpc  = 4647
  serf = 4648
}

advertise {
  http = "10.10.10.30"
  rpc  = "10.10.10.30"
  serf = "10.10.10.30"
}

acl {
  enabled = true
}

tls {
  http                  = true
  rpc                   = true
  verify_server_hostname = true
  verify_https_client   = false
  ca_file               = "/etc/mcp/nomad/tls/nomad-agent-ca.pem"
  cert_file             = "/etc/mcp/nomad/tls/nomad-agent.pem"
  key_file              = "/etc/mcp/nomad/tls/nomad-agent-key.pem"
}

telemetry {
  publish_allocation_metrics = true
  publish_node_metrics       = true
}

ui {
  enabled = true
}


client {
  enabled    = true
  node_class = "build"
  servers = ["10.10.10.40:4647"]

  meta {
    workload_pool = "build"
  }
}

plugin "docker" {
  config {
    allow_privileged = false

    volumes {
      enabled = true
    }
  }
}
