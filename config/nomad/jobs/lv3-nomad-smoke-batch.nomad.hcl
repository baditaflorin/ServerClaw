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
          "echo \"$NOMAD_META_message\" && date -Iseconds",
        ]
      }

      resources {
        cpu    = 100
        memory = 64
      }
    }
  }
}
