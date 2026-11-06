#!/usr/bin/env bash
# Boot each variant tree of the tailscaled-restart rig in a throwaway systemd container, restart the stand-in tailscaled the ways a real one restarts
# and report which proxy sockets stay dead. Run it on a Linux build host with docker (never on a hypervisor):
#   python3 scripts/tailscaled_restart_rig/build_variants.py --out TREES      (anywhere; renders the real templates)
#   scripts/tailscaled_restart_rig/run.sh TREES [debian-tag ...]               (default: trixie; bookworm is the 0docker systemd)
# Default variants: the five 0mcp ones (role-none ... hostconf-fix) on every base, plus the four 0docker ones (docker0-live ... docker0-fix) on bookworm; RIG_VARIANTS="a b" runs exactly those.
# Exit status 0 only when every "fix" variant keeps all its sockets and the baselines ("role-none", "docker0-live") show the failure (so the rig really reproduces it).
set -u -o pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
TREES=${1:?usage: run.sh TREES_DIR [debian-tag ...]}
shift
BASES=("$@")
[ ${#BASES[@]} -gt 0 ] || BASES=(trixie)
VARIANTS_0MCP="role-none role-freebind role-wants role-fix hostconf-fix"
VARIANTS_0DOCKER="docker0-live docker0-freebind docker0-wants docker0-fix" # the 0docker hypervisor runs systemd 252 = debian:bookworm
RUN_ID=$$
RESULTS=$(mktemp)
containers=()

cleanup() {
  for c in "${containers[@]:-}"; do [ -n "$c" ] && docker rm -f "$c" >/dev/null 2>&1; done
  rm -f "$RESULTS"
}
trap cleanup EXIT

record() { # base variant event outcome
  printf '%-9s %-14s %-22s %s\n' "$1" "$2" "$3" "$4" | tee -a "$RESULTS"
}

# The image is defined inline, not as a Dockerfile in the tree: a container whose PID 1 is systemd has to run as root, which the repo's trivy gate (DS-0002, no USER) rightly
# rejects for a service image and which is not a finding for this throwaway test image.
for base in "${BASES[@]}"; do
  docker build -q --build-arg "BASE=$base" -t "tsrig:$base" -f - "$HERE" >/dev/null <<'DOCKERFILE' || { echo "image build failed for $base" >&2; exit 2; }
# Throwaway systemd image for the tailscaled-restart rig (the same systemd as the hypervisors: bookworm = 252 as on 0docker, trixie = 257 as on 0mcp).
ARG BASE=trixie
FROM debian:${BASE}
ENV container=docker DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends systemd systemd-sysv udev iproute2 procps ca-certificates \
 && apt-get clean && rm -rf /var/lib/apt/lists/*
# systemd-udev-trigger is masked on purpose: in a privileged container /sys is the host's, and a trigger there would replay "add" uevents for the host's devices.
# The container's own udevd still sees the uevents of devices created in the container's network namespace, which is all the rig needs (tailscale0).
RUN for unit in systemd-udev-trigger.service systemd-networkd.service systemd-networkd.socket systemd-networkd-wait-online.service \
      systemd-resolved.service systemd-logind.service getty.target console-getty.service getty@tty1.service \
      systemd-udevd.service systemd-udevd-control.socket systemd-udevd-kernel.socket systemd-udevd-varlink.socket; do \
      ln -sf /dev/null /etc/systemd/system/$unit; done
COPY rig-init /usr/local/bin/rig-init
STOPSIGNAL SIGRTMIN+3
CMD ["/usr/local/bin/rig-init"]
DOCKERFILE
  if [ -n "${RIG_VARIANTS:-}" ]; then
    read -r -a VARIANTS <<<"$RIG_VARIANTS"
  else
    read -r -a VARIANTS <<<"$VARIANTS_0MCP $([ "$base" = bookworm ] && echo "$VARIANTS_0DOCKER")"
  fi
  for variant in "${VARIANTS[@]}"; do
    c="tsrig-$RUN_ID-$base-$variant"
    containers+=("$c")
    docker create --privileged --network none --tmpfs /run --tmpfs /run/lock --name "$c" "tsrig:$base" >/dev/null || exit 2
    docker cp "$TREES/$variant/." "$c:/" || exit 2
    docker start "$c" >/dev/null || exit 2
    dx() { docker exec "$c" "$@"; }

    # boot: wait for the system to finish starting (degraded is fine: the stand-in has no network), then for the sockets
    for _ in $(seq 1 60); do
      state=$(dx systemctl is-system-running 2>/dev/null)
      [ "$state" = running ] || [ "$state" = degraded ] && break
      sleep 1
    done
    record "$base" "$variant" "boot (systemd $(dx systemctl --version | head -1 | cut -d' ' -f2))" "$(dx rig-settle 20)"
    # the units must be valid for this systemd (warnings about the stand-in's own paths are not interesting, anything else is)
    problems=$(dx sh -c 'cd /etc/systemd/system && systemd-analyze verify --man=no tailscaled.service $(cat /etc/rig-sockets) 2>&1' | grep -v -E "^$" | head -5)
    record "$base" "$variant" "systemd-analyze verify" "${problems:-clean}"
    # the two properties hostconf proves the drop-ins by (config/hostconf/hostconf.yaml: expect): FreeBind of each socket, Wants of the device unit
    freebind=$(dx sh -c 'for u in $(cat /etc/rig-sockets); do printf "%s " "$(systemctl show -p FreeBind --value "$u")"; done')
    wants=$(dx systemctl show -p Wants --value sys-subsystem-net-devices-tailscale0.device | tr ' ' '\n' | grep -c 'socket$')
    record "$base" "$variant" "hostconf properties" "FreeBind: ${freebind}| tailscale0 Wants: ${wants} sockets"

    dx systemctl restart tailscaled
    record "$base" "$variant" "restart (apt upgrade)" "$(dx rig-settle 12)"

    pid=$(dx systemctl show -p MainPID --value tailscaled)
    dx kill -9 "$pid"
    sleep 0.3
    record "$base" "$variant" "crash (kill -9)" "$(dx rig-settle 12)"

    dx systemctl stop tailscaled
    sleep 2
    dx systemctl start tailscaled
    record "$base" "$variant" "stop, 2 s, start" "$(dx rig-settle 12)"

    # an operator who stops one proxy socket on purpose must not see it come back by itself (Wants= is a one-time pull, unlike Upholds=)
    operator_socket=$(dx cat /etc/rig-operator-socket 2>/dev/null)
    if [ -n "$operator_socket" ]; then
      dx systemctl stop "$operator_socket"
      sleep 3
      record "$base" "$variant" "operator stop stays" "$(dx systemctl is-active "$operator_socket")"
    fi
    reasons=$(dx journalctl -b -o cat --no-pager 2>/dev/null | grep -E "Bound to unit|Cannot assign requested|ordering cycle|to break ordering" | sed -E 's/[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:[0-9]+/ADDR/; s/lv3-tailscale-proxy-[a-z0-9-]+/lv3-tailscale-proxy-X/' | sort | uniq -c | sed 's/^ */    /')
    [ -n "$reasons" ] && { echo "  journal ($base $variant):"; echo "$reasons"; }
    docker rm -f "$c" >/dev/null 2>&1
  done
done

echo
fail=0
for base in "${BASES[@]}"; do
  # every fix variant: all events ok; every baseline that was run: at least one event leaves sockets dead (the rig reproduces the incident, or the exposure still open)
  if grep -E "^$base +(role-fix|hostconf-fix|docker0-fix) " "$RESULTS" | grep -E "restart|crash|stop, 2 s|boot" | grep -q DEAD; then echo "FAIL $base: a fix variant left sockets dead"; fail=1; fi
  for baseline in role-none docker0-live; do
    grep -q -E "^$base +$baseline " "$RESULTS" || continue
    if ! grep -E "^$base +$baseline " "$RESULTS" | grep -E "restart|crash|stop, 2 s" | grep -q DEAD; then echo "FAIL $base: $baseline did not reproduce the failure"; fail=1; fi
  done
  if grep -E "^$base +(role-fix|hostconf-fix|docker0-fix) +operator stop stays" "$RESULTS" | grep -v -q inactive; then echo "FAIL $base: an operator's stop did not stay"; fail=1; fi
done
[ $fail -eq 0 ] && echo "RIG OK: the fix keeps every proxy socket across restart, crash and stop/start; the baseline loses them"
exit $fail
