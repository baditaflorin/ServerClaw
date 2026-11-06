#!/usr/bin/env bash
# Run INSIDE the 0own runtime VM (660) as root. Installs the Docker log shipper (Vector) that copies the logs of the ct-names container -- and only
# that container -- to the central OpenObserve stream docker_logs (https://openobserve.0own.com). The VM has no shipper today, and its other ~50
# containers are left out on purpose: shipping them would add writes to the same spinning mirror OpenObserve itself lives on. Widening it later is one
# edit of include_containers.
# Credentials: ONE JSON object on stdin, {"user":"...","password":"..."}, never argv or environment. They go only into the root-only (0600) Vector
# config. Validate first, keep the previous config as a rollback copy, restore it if the new agent does not start.
#   printf ... | install-log-shipper.sh            plan only (validates the stdin shape, prints what it would do)
#   ... | install-log-shipper.sh --apply
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/observability/vector-log-shipper}"
IMAGE="${IMAGE:-timberio/vector@sha256:e4fc19efb7f817f28d06a9a67fab9e1ccc60d57080115c291b06deb6daea7d7a}"   # the digest services-registry's observability installer pins
ENDPOINT="${ENDPOINT:-https://openobserve.0own.com/api/default/docker_logs/_json}"
FLEET="${FLEET:-0own}"; HOST_LABEL="${HOST_LABEL:-0own-runtime}"; ROLE="${ROLE:-pool-runtime}"
CONTAINERS="${CONTAINERS:-go-ct-names}"    # comma separated name prefixes

apply=0
case "${1:-}" in "") ;; --apply) apply=1 ;; *) echo "usage: printf '{\"user\":..,\"password\":..}' | $0 [--apply]" >&2; exit 2 ;; esac

creds="$(cat)"
render() {
  CREDS="$creds" python3 - "$ENDPOINT" "$FLEET" "$HOST_LABEL" "$ROLE" "$CONTAINERS" <<'PY'
import json, os, sys
endpoint, fleet, host, role, containers = sys.argv[1:6]
c = json.loads(os.environ["CREDS"])
user, password = c["user"], c["password"]
assert isinstance(user, str) and user and isinstance(password, str) and password
q = json.dumps
inc = ", ".join(q(x.strip()) for x in containers.split(",") if x.strip())
print(f'''# Rendered by platform_server config/0own/ct-names/install-log-shipper.sh
data_dir = "/var/lib/vector"

[sources.docker]
type = "docker_logs"
include_containers = [{inc}]

[transforms.enrich]
type = "remap"
inputs = ["docker"]
source = \'\'\'
.fleet = {q(fleet)}
.host = {q(host)}
.role = {q(role)}
.collector = "vector-log-shipper"
.observability_schema = "1"
\'\'\'

[sinks.openobserve]
type = "http"
inputs = ["enrich"]
uri = {q(endpoint)}
method = "post"
auth.strategy = "basic"
auth.user = {q(user)}
auth.password = {q(password)}
compression = "gzip"
encoding.codec = "json"
encoding.timestamp_format = "rfc3339"
healthcheck.enabled = false

[sinks.openobserve.batch]
max_events = 500
timeout_secs = 5

[sinks.openobserve.buffer]
type = "disk"
max_size = 1073741824
when_full = "block"''')
PY
}
next_conf="$(render)" || { echo "stdin must be one JSON object with non-empty string fields user and password" >&2; exit 1; }
unset creds

compose="services:
  vector-log-shipper:
    image: ${IMAGE}
    container_name: vector-log-shipper
    command: [\"--config\", \"/etc/vector/vector.toml\"]
    network_mode: host
    restart: always
    logging:
      driver: json-file
      options:
        max-size: 20m
        max-file: 2
    volumes:
      - ./vector.toml:/etc/vector/vector.toml:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - vector_data:/var/lib/vector

volumes:
  vector_data:
"

if [ "$apply" != 1 ]; then
  echo "Plan only: would write ${INSTALL_DIR}/vector.toml (0600, containers: ${CONTAINERS}, fleet ${FLEET}, host ${HOST_LABEL}) and docker-compose.yml,"
  echo "validate with the pinned image, start it, and roll back if it does not run. Re-run with --apply."
  exit 0
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 0700 "$INSTALL_DIR"
cd "$INSTALL_DIR"
( umask 077; printf '%s\n' "$next_conf" > vector.toml.next )
unset next_conf
printf '%s' "$compose" > docker-compose.yml.next
previous_running="$(docker inspect -f '{{.State.Running}}' vector-log-shipper 2>/dev/null || printf false)"
if ! docker run --rm --network host -v "$PWD/vector.toml.next:/etc/vector/vector.toml:ro" "$IMAGE" validate --no-environment /etc/vector/vector.toml >/dev/null 2>&1; then
  rm -f vector.toml.next docker-compose.yml.next
  echo "Vector config validation failed; the current agent is unchanged" >&2; exit 1
fi
[ ! -e vector.toml ] || cp -a vector.toml "vector.toml.rollback-${stamp}"
[ ! -e docker-compose.yml ] || cp -a docker-compose.yml "docker-compose.yml.rollback-${stamp}"
mv -f vector.toml.next vector.toml; mv -f docker-compose.yml.next docker-compose.yml; chmod 0600 vector.toml
if docker compose up -d --force-recreate && [ "$(docker inspect -f '{{.State.Status}}' vector-log-shipper 2>/dev/null || true)" = running ]; then
  echo "Vector is running on ${HOST_LABEL} (containers: ${CONTAINERS})"; exit 0
fi
echo "Vector replacement failed; restoring the previous config" >&2
if [ -e "vector.toml.rollback-${stamp}" ]; then mv -f "vector.toml.rollback-${stamp}" vector.toml; else rm -f vector.toml; fi
if [ -e "docker-compose.yml.rollback-${stamp}" ]; then mv -f "docker-compose.yml.rollback-${stamp}" docker-compose.yml; else rm -f docker-compose.yml; fi
if [ "$previous_running" = true ]; then docker compose up -d --force-recreate || true; else docker rm -f vector-log-shipper >/dev/null 2>&1 || true; fi
exit 1
