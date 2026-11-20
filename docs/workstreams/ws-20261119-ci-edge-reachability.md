# Workstream: Restore public NGINX edge and Woodpecker reachability

## Incident

On 2026-11-19, `https://ci.example.com` refused TCP connections on port 443, so
the repository activation helper and outside clients could not reach the
dedicated Woodpecker control plane.

## Evidence and cause

- DNS resolved `ci.example.com` to the public edge.
- The Proxmox host had active firewall and DNAT rules forwarding public ports
  80 and 443 to the NGINX edge VM.
- Woodpecker on the Docker runtime VM was healthy. Its local API returned
  HTTP 401 without credentials, confirming that its HTTP listener was alive.
- The NGINX edge VM's `/etc/nginx/nginx.conf` included only
  `/etc/nginx/conf.d/*.conf`. Managed site files, including the CI HTTP and
  HTTPS vhosts, were present in `/etc/nginx/sites-enabled/` but were not loaded.
  `nginx -T` therefore showed only the default server and NGINX listened on
  port 80 without a listener on 443.
- A temporary config adding `include /etc/nginx/sites-enabled/*;` passed
  `nginx -t`; the only output was duplicate MIME type warnings.

The effective root cause was the missing sites-enabled include in the main
NGINX config. This allowed the current `nginx -t` to pass while validating only
the default server, leaving all managed edge vhosts inactive.

## Change

The `nginx_edge_publication` role now ensures that the main NGINX config loads
`/etc/nginx/sites-enabled/*` after its `conf.d` include. The edge runbook records
why this include is required when the installed NGINX package uses upstream
defaults.

## Verification

The canonical production converge completed at 2026-11-19 15:34:26 UTC with
`ok=165`, `changed=6`, `unreachable=0`, and `failed=0`. It loaded the managed
site vhosts and opened NGINX listeners on ports 80 and 443. `nginx -t` passed;
all 36 edge certificates validated. Public `https://ci.example.com/healthz`
returned HTTP 204 with a valid TLS chain. The unauthenticated `/api/user`
endpoint returned HTTP 401, as expected for a live authenticated API.

The apply receipt exposed a separate tracking defect: when PyYAML was absent,
the receipt writer saved JSON under a `.json` name while its reader only looked
for `.yaml`. The completion step therefore lost the start time and metadata.
`platform/workstream_receipts.py` now finds existing YAML or JSON receipts and
updates the same format.

After PR #710 merged, a fresh worktree from `origin/main` was converged again
at 2026-11-19 16:43:06 UTC. It completed with `ok=165`, `changed=5`,
`unreachable=0`, and `failed=0`. All 36 edge certificates validated, public
health returned HTTP 204 with TLS verification result 0, the unauthenticated
API returned HTTP 401 as expected, and NGINX listened on ports 80 and 443 with
`nginx -t` passing. The refreshed apply receipt captured 16:38:21–16:43:06 UTC,
or 4m45s.

The original apply start cannot be recovered because the JSON fallback
discarded it. The first retained Ansible timestamp was 15:31:42 UTC and that
apply completed at 15:34:26 UTC, a 2m44s verified window that excludes earlier
diagnosis and setup. The mainline reapply is precisely timed above. No
infrastructure was added or resized, so there was no incremental provider
charge; local compute, power, and operator time are not separately metered.

The public API token check from the fleet automation host succeeded and
confirmed that the GitHub repository is already active on the dedicated CI
plane. Both Woodpecker contexts passed on PR #710:
`ci/woodpecker/push/woodpecker` and
`ci/woodpecker/pr/woodpecker`.
