# Rebuild manually-built images (no CI publish step)

## Purpose

A handful of services on `docker-runtime` (VMID 120) have no automated
build/publish pipeline at all — no GitHub Actions, and their
`.woodpecker.yml` (where one exists) only runs tests, never a `docker build`
or `docker push`. Their images exist only because someone ran `docker build`
by hand at some point and the result sat in the local image cache and/or a
registry. If that cache is ever lost (see the 2026-08-27 postmortem update
in `docs/postmortems/2026-08-26-0mcp-nginx-edge-network-outage.md` for how
that happened — a `cloud-init` bug wiped `docker-runtime`'s entire image
cache), there is no automated way to get the image back. This runbook is
the reconstructed manual process, so the next incident doesn't require
re-deriving it from scratch.

## Known affected services

| Service | Image | Source location | Registry |
|---|---|---|---|
| `mcp-site-service` | `ghcr.io/baditaflorin/mcp-site-service:latest` | `/opt/mcp-site-service` (plain deployed tree, no `.git`) | GHCR, private repo |
| `browser-runner` | `lv3/browser-runner:latest` | `/opt/browser-runner/app` (has a `Dockerfile`) | none — purely local tag, never pushed anywhere |
| `ops-portal` | `0mpc-ops-portal:latest` | built via `docker compose up -d`'s own `build:` directive in `/opt/ops-portal/docker-compose.yml` | none — purely local tag |

`ops-portal` self-heals on `docker compose up -d` since its compose file has
a `build:` stanza; the other two need a manual `docker build` first.

## Commands

### mcp-site-service (private GHCR image)

The docker host needs GHCR credentials — a personal access token with at
least `write:packages` scope works (GitHub's docs confirm `write:packages`
also grants pull access):

```bash
GH_TOKEN=$(gh auth token)
ssh 0mcp_docker "sudo docker login ghcr.io -u baditaflorin --password-stdin" <<< "$GH_TOKEN"
```

Rebuild from whatever source is already checked out at `/opt/mcp-site-service`
(tag both `:latest` and the current `VERSION` file's contents so there's a
pinned fallback too):

```bash
ssh 0mcp_docker "cd /opt/mcp-site-service && \
  sudo docker build -t ghcr.io/baditaflorin/mcp-site-service:latest \
                     -t ghcr.io/baditaflorin/mcp-site-service:\$(cat VERSION) ."
ssh 0mcp_docker "sudo docker push ghcr.io/baditaflorin/mcp-site-service:latest"
ssh 0mcp_docker "sudo docker push ghcr.io/baditaflorin/mcp-site-service:\$(cat VERSION)"
ssh 0mcp_docker "cd /opt/mcp-site-service && sudo docker compose up -d"
```

### browser-runner (purely local image, never published anywhere)

```bash
ssh 0mcp_docker "cd /opt/browser-runner/app && sudo docker build -t lv3/browser-runner:latest ."
ssh 0mcp_docker "cd /opt/browser-runner && sudo docker compose up -d"
```

## Verification

```bash
curl -sk -o /dev/null -w "%{http_code}\n" https://app.example.org   # mcp-site-service, expect 200
ssh 0mcp_docker "sudo docker ps --filter name=browser-runner --format '{{.Names}}: {{.Status}}'"
```

## Follow-up

Neither of these images has any registry-side source of truth beyond
whatever is currently checked out on `docker-runtime` itself. If that
guest's disk were ever lost (not just its Docker state), `browser-runner`
would need its `Dockerfile`/source recovered from a backup or rewritten,
and `mcp-site-service` would need a fresh clone of
`baditaflorin/mcp-site-service` at whatever commit was last actually
deployed (not necessarily `main` — there's no deploy-tracking mechanism
that records which commit is live). Worth deciding whether these deserve
an actual CI publish step (Woodpecker already runs on this fleet and
wouldn't cost GitHub Actions billing) rather than staying fully manual.
