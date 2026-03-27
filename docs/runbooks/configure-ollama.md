# Configure Ollama

## Purpose

This runbook converges the private Ollama runtime defined by ADR 0145 and verifies
that local inference is reachable on `docker-runtime-lv3`.

## Result

- `docker-runtime-lv3` runs Ollama from `/opt/ollama`
- model weights persist under `/data/ollama/models`
- the repo-managed startup models from `config/ollama-models.yaml` are pulled during converge
- Open WebUI can reach the local inference API through `host.docker.internal:11434`
- the goal compiler can use `platform/llm/client.py` for bounded local-normalisation fallback
- controller-local latency probes run through a temporary SSH tunnel to the private guest endpoint

## Commands

Syntax-check the Ollama workflow:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make syntax-check-ollama
```

Converge the private runtime on `docker-runtime-lv3`:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make converge-ollama
```

## Verification

Verify the runtime health endpoint on the guest:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.118.189.95 \
  ops@10.10.10.20 \
  'curl -fsS http://127.0.0.1:11434/api/version'
```

Verify the default startup model is present:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.118.189.95 \
  ops@10.10.10.20 \
  'sudo docker exec ollama ollama show llama3.2:3b'
```

Measure local inference latency from the controller through a temporary SSH tunnel:

```bash
ssh -fN \
  -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -L 11434:127.0.0.1:11434 \
  -J ops@100.118.189.95 \
  ops@10.10.10.20

cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
uv run --with pyyaml python scripts/ollama_probe.py --base-url http://127.0.0.1:11434 --runs 3 --json

pkill -f 'ssh -fN .*11434:127.0.0.1:11434'
```

Verify Open WebUI can still sign in after the local connector is enabled:

```bash
curl -s -X POST http://100.118.189.95:8008/api/v1/auths/signin \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"ops@lv3.org\",\"password\":\"$(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/open-webui/admin-password.txt)\"}"
```

## Operating Notes

- Keep Ollama private to the docker-runtime VM and the LV3 internal guest network; do not publish it through the public edge.
- The current repo-managed startup model is `llama3.2:3b` because it fits the goal-compiler fallback use case without requiring a GPU.
- Additional models may be declared in `config/ollama-models.yaml`, but only mark them `pull_on_startup: true` when the extra RAM and disk footprint are justified.
