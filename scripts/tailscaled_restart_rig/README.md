# tailscaled-restart rig

A throwaway systemd container that reproduces what a tailscaled restart did to the 0mcp and 0docker hypervisors' tailnet proxy sockets on 2026-11-02, and proves the fix. See
`docs/runbooks/tailscaled-restart-proxies.md` for the incident and the fix; `tests/test_tailscaled_restart_proxies.py` (0mcp) and `tests/test_tailscaled_restart_0docker.py` (0docker) keep the lists the fix is made of from drifting.

- `build_variants.py` renders the real role templates and copies the real hostconf files into five unit trees for 0mcp (an ablation: nothing, FreeBind only, the tailscale0 `Wants=` drop-in only, both,
  and the live layout of the hypervisor: old main units plus hostconf drop-ins) and four for 0docker (`docker0-live`, `docker0-freebind`, `docker0-wants`, `docker0-fix`: an ablation on top of what is live there, with the
  hand-installed `woodpecker-exec-proxy@.socket` and `.service` in `0docker-units/` copied verbatim from the host on 2026-11-03, the node-exporter proxy rendered by the role, and the 0docker tailnet address). It touches no host.
- `run.sh` boots each tree in a privileged container (`--network none`, systemd 257 from `debian:trixie` as on 0mcp, systemd 252 from `debian:bookworm` as on 0docker) with a stand-in `tailscaled`
  that reports ready first, creates `tailscale0` 50 ms later and gives it the tailnet address 0.8 s after that (the timing of the real restart, from its journal), then restarts it four ways
  (boot, `systemctl restart`, `kill -9`, `stop` + `start`) and prints which sockets are dead. It exits 0 only when every fix variant (`role-fix`, `hostconf-fix`, `docker0-fix`) keeps all its sockets and the baselines
  (`role-none`, `docker0-live`) show the failure. The 0mcp variants run on every base; the `docker0-*` ones by default only on `bookworm` (systemd 252, as on the 0docker hypervisor).
- the image is defined inline in `run.sh` (systemd as PID 1 must run as root, which the repo's trivy gate rejects for a Dockerfile in the tree), with `rig-init` as its PID 1: a wrapper that starts udevd before
  systemd (systemd only follows udev, and so only creates `.device` units, when udevd is already running as it starts). `systemd-udev-trigger` is masked on purpose: in a privileged container `/sys` is the
  host's, and a trigger would replay uevents for the host's devices.

Run it on a Linux build host with docker, never on a hypervisor:

```sh
uv run --with jinja2 python3 scripts/tailscaled_restart_rig/build_variants.py --out /var/tmp/tsrig/trees
scripts/tailscaled_restart_rig/run.sh /var/tmp/tsrig/trees trixie bookworm      # about 12 minutes (5 variants on trixie, 9 on bookworm), load stays low
```

On the build host use `/var/tmp`, not `/tmp` (a RAM tmpfs there). `RIG_VARIANTS="role-none role-fix"` runs a subset (and on any base, e.g. `RIG_VARIANTS="docker0-live docker0-fix" run.sh TREES trixie`). The containers are named `tsrig-<pid>-<base>-<variant>` and removed at the end.
