# ADR 0284: Piper TTS As The CPU Neural Text-To-Speech Service

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: pending merge to main
- Implemented In Platform Version: 0.130.74
- Implemented On: 2026-03-31
- Date: 2026-03-29

## Context

The platform's agent and automation layers produce text output exclusively.
ServerClaw (ADR 0254) operates as a conversational agent, Windmill workflows
send notifications, and ntfy delivers push alerts. None of these can produce
spoken audio output.

A fully autonomous platform operating without human eyes on a screen needs a
voice output path so that agents can:

- read back summaries or status updates over a voice channel
- narrate alert content when screen attention is unavailable
- drive a voice-UI for hands-free operator interaction
- feed synthesised speech into Livekit rooms for real-time agent voice calls

GPU-based TTS models are expensive to run continuously. Piper is a CPU-only
neural TTS engine developed by the Home Assistant project. It uses ONNX-runtime
for inference and produces near-natural speech at real-time factor on a single
CPU core using the `en_US-ryan-medium` or equivalent model. The full service
binary is under 50 MB; models are 50–500 MB depending on quality.

## Decision

We will deploy **Piper TTS** as the canonical CPU neural text-to-speech service.

### Deployment rules

- Piper runs as a Docker Compose service on the docker-runtime VM exposing an
  HTTP API (`/api/tts`) that accepts text and returns WAV audio
- voice model files are stored on a named Docker volume; models are declared
  in the Ansible role defaults and downloaded on first converge
- the service is internal-only; no public subdomain is issued
- no secrets are required; access is restricted to the guest network

### API contract

- callers POST plain text to `/api/tts` and receive `audio/wav` in response
- the model and voice are selected by query parameter; the default model is
  declared in the Ansible role and can be overridden per request
- callers are responsible for streaming or storing the returned WAV bytes;
  Piper itself does not persist audio

### Consumer conventions

- ServerClaw voice sessions route synthesised responses through Piper before
  delivering audio over a Livekit channel (ADR 0293)
- Windmill workflows that produce operator-facing summaries may call Piper to
  produce a spoken version for delivery via ntfy audio attachment
- no service should bundle a separate TTS engine when Piper is available

## Consequences

**Positive**

- Voice output is available to all platform services through a single shared
  endpoint without any GPU dependency.
- Piper's ONNX runtime runs inference at real-time speed on a single CPU core,
  making it practical as a continuously available sidecar.
- Multiple voice models can coexist on the same volume; model selection is a
  per-request parameter, not a service restart.
- The CPU-only footprint means Piper can be co-located on the docker-runtime
  VM without competing with GPU-bound workloads.

**Negative / Trade-offs**

- Piper's medium-quality models produce near-natural but not indistinguishable
  speech; high-expressiveness applications may find quality limiting.
- Concurrent synthesis requests share a single CPU; request queuing must be
  accounted for in latency-sensitive call paths.

## Boundaries

- Piper is the TTS service only; it does not perform speech recognition,
  language detection, or audio storage.
- Piper does not replace ntfy or Mattermost for text notifications; it adds a
  voice output path for callers that need audio.
- Piper is not used for bulk audio production or podcast-scale synthesis; it
  is a real-time per-request service.

## Related ADRs

- ADR 0124: Ntfy for push notifications
- ADR 0254: ServerClaw as a distinct self-hosted agent product on LV3
- ADR 0285: Whisper ASR as the CPU speech-to-text service
- ADR 0293: Livekit as the real-time audio and voice channel for agents

## References

- <https://github.com/rhasspy/piper>
