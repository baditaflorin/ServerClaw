job "lv3-nomad-smoke-service" {
  region      = "global"
  datacenters = ["dc1"]
  type        = "service"

  constraint {
    attribute = "${node.class}"
    operator  = "="
    value     = "build"
  }

  group "http" {
    count = 1

    network {
      mode = "host"

      port "http" {
        static = 18180
      }
    }

    restart {
      attempts = 10
      interval = "30m"
      delay    = "15s"
      mode     = "delay"
    }

    task "http" {
      driver = "docker"

      config {
        image   = "python:3.13-alpine3.22"
        command = "sh"
        args = [
          "-lc",
          "mkdir -p /srv/www && printf 'lv3 nomad smoke service\\n' > /srv/www/index.html && exec python3 -m http.server 18180 --bind 0.0.0.0 --directory /srv/www",
        ]
        ports = ["http"]
      }

      resources {
        cpu    = 100
        memory = 128
      }

      service {
        name = "lv3-nomad-smoke-service"
        port = "http"
        tags = ["repo-managed", "adr-0232", "smoke"]
      }
    }
  }
}
