job "lv3-nomad-smoke-batch" {
  region      = "global"
  datacenters = ["dc1"]
  type        = "batch"

  parameterized {
    meta_required = ["message"]
  }

  constraint {
    attribute = "${node.class}"
    operator  = "="
    value     = "runtime"
  }

  group "dispatch" {
    task "echo" {
      driver = "docker"

      config {
        image   = "busybox:1.36.1"
        command = "sh"
        args = [
          "-lc",
          "mkdir -p /verification && printf '%s\n' \"$NOMAD_META_message\" > /verification/last-run.log && date -Iseconds >> /verification/last-run.log && cat /verification/last-run.log",
        ]
        volumes = ["/var/lib/nomad/verification/lv3-nomad-smoke-batch:/verification"]
      }

      resources {
        cpu    = 100
        memory = 64
      }
    }
  }
}
