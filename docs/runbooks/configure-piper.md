# Configure Piper

## Purpose

This runbook converges the private Piper text-to-speech runtime from ADR 0284
and verifies the guest-network `/api/tts` WAV synthesis contract end to end.

## Result

- `docker-runtime-lv3` runs Piper from `/opt/piper`
- Piper listens privately on `10.10.10.20:8099`
- the repo-managed default voice is downloaded into the named Docker volume `piper-models`
- callers can POST plain text to `/api/tts` and receive `audio/wav` without publishing a public hostname

## Commands

Syntax-check the Piper workflow:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make syntax-check-piper
```

Converge the Piper runtime directly:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make converge-piper env=production
```

Run the governed live-apply wrapper:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=piper env=production
```

## Verification

Verify the private Piper health endpoint on `docker-runtime-lv3`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'curl -fsS http://127.0.0.1:8099/healthz'
```

Verify the declared voice list:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'curl -fsS http://127.0.0.1:8099/api/voices'
```

Verify Piper synthesizes WAV audio from the ADR contract:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'python3 - <<'"'"'PY'"'"'
import json
import urllib.request

request = urllib.request.Request(
    "http://127.0.0.1:8099/api/tts?voice=en_US-ryan-medium",
    data=b"LV3 Piper runbook verification",
    headers={"Content-Type": "text/plain; charset=utf-8"},
    method="POST",
)
with urllib.request.urlopen(request, timeout=180) as response:
    payload = response.read()
    content_type = response.headers.get("Content-Type", "")

assert content_type.startswith("audio/wav"), content_type
assert payload[:4] == b"RIFF", payload[:8]
assert payload[8:12] == b"WAVE", payload[:16]
assert len(payload) > 1024, len(payload)
print(json.dumps({"verified": True, "bytes": len(payload)}))
PY'
```

## Operating Notes

- There is no public hostname for Piper. Keep it on the private guest network only.
- Piper is intentionally private-only. Do not publish it on the public NGINX edge.
- The current repo-managed default voice is `en_US-ryan-medium`; add future voice models in the role defaults and replay the converge rather than downloading them ad hoc on the guest.
- The runtime stores model files on the named Docker volume `piper-models`, but it does not persist synthesized WAV output.
- The role builds the runtime image from repo-managed sources on the guest so the `/api/tts` contract stays version-controlled and does not depend on an opaque third-party HTTP wrapper.
