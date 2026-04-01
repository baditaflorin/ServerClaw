# ADR 0293: Livekit As The Real-Time Audio And Voice Channel For Agents

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: 0.177.132
- Implemented In Platform Version: 0.130.83
- Implemented On: 2026-04-01
- Date: 2026-03-29

## Context

The platform's autonomous agent layer (ServerClaw, ADR 0254) currently
operates exclusively over text channels: Mattermost messages, API calls, and
Windmill workflow triggers. There is no real-time, bidirectional voice channel
through which an operator can speak to an agent and receive a spoken response.

The voice pipeline components exist in isolation:

- Piper TTS (ADR 0284) can synthesise speech from text
- Whisper ASR (ADR 0285) can transcribe audio to text

What is missing is a real-time media transport layer that:

- carries audio between the operator's browser and the platform
- handles WebRTC signalling, DTLS/SRTP encryption, and adaptive bitrate
- manages room lifecycle (create room, join, leave, disconnect)
- allows the agent to publish synthesised audio and subscribe to operator audio
  as first-class media tracks

Without a media server, voice interaction requires custom WebRTC code in every
client and has no server-side participant for the agent to join.

Livekit is a CPU-capable open-source WebRTC SFU (Selective Forwarding Unit)
and media server. Its Go-based server handles signalling and media forwarding
entirely on CPU. The Livekit Agents framework provides Python bindings that
allow a ServerClaw session to join a Livekit room as a participant, subscribe
to the operator's audio, pipe it through Whisper ASR, and publish Piper TTS
output back — creating a complete, low-latency voice conversation loop without
any GPU.

## Decision

We will deploy **Livekit** as the real-time audio and voice channel for agent
voice sessions.

### Deployment rules

- Livekit server runs as a Docker Compose service on the docker-runtime VM
- it is published at the NGINX edge for WebRTC access (ADR 0021); WebRTC
  requires both the signalling WebSocket and media UDP port ranges to be
  reachable from the operator's browser
- API keys for room creation and agent participant tokens are stored in
  OpenBao and injected following ADR 0077
- the service is available at `livekit.<domain>` for the signalling endpoint

### Voice session architecture

- when an operator initiates a voice session with ServerClaw, a Windmill
  workflow creates a Livekit room and issues a participant token
- the ServerClaw agent process joins the room using the Livekit Agents Python
  SDK as a server-side participant
- operator audio → Livekit room → agent subscribes → Whisper ASR (ADR 0285)
  → LiteLLM (ADR 0287) → LLM response text → Piper TTS (ADR 0284) → agent
  publishes audio track → Livekit room → operator hears response
- the complete loop operates on CPU; no GPU is required at any stage

### Room governance

- rooms are ephemeral; they are created per session and destroyed on
  disconnect
- room metadata carries the agent session ID for correlation with Langfuse
  traces (ADR 0146)
- room recordings are not enabled by default; recording is an opt-in operator
  action stored in MinIO (ADR 0274)

## Consequences

**Positive**

- The platform gains a complete CPU-only voice loop: operator speaks, agent
  hears, reasons, and speaks back — all without a GPU.
- Livekit's WebRTC transport handles NAT traversal, encryption, and adaptive
  bitrate without custom media code.
- The Livekit Agents framework makes the server-side agent participant a
  first-class SDK pattern, not a custom integration.
- Room-based architecture means multiple concurrent voice sessions are
  isolated from one another with independent media tracks.

**Negative / Trade-offs**

- WebRTC media UDP ports must be open at the edge firewall; this expands the
  platform's public network surface beyond the current TCP-only NGINX profile.
- End-to-end voice latency depends on ASR processing time (Whisper base ~1–2 s
  on CPU) plus LLM inference time; sub-second conversation cadence is not
  achievable at current model sizes.

## Boundaries

- Livekit is the real-time audio transport and signalling layer; it does not
  replace Mattermost for asynchronous text communication.
- Livekit does not replace Piper TTS or Whisper ASR; it is the media channel
  between them, not the inference engine.
- Livekit is not used for video conferencing or screen sharing at launch;
  only audio tracks are enabled in the initial agent voice session profile.
- Livekit is not used for broadcast streaming; it handles point-to-point and
  small-room real-time sessions only.

## Related ADRs

- ADR 0021: Public subdomain publication at the NGINX edge
- ADR 0077: Compose secrets injection pattern
- ADR 0146: Langfuse for agent observability
- ADR 0254: ServerClaw as a distinct self-hosted agent product on LV3
- ADR 0274: MinIO as the S3-compatible object storage layer
- ADR 0284: Piper TTS as the CPU neural text-to-speech service
- ADR 0285: Whisper ASR as the CPU speech-to-text service
- ADR 0287: LiteLLM as the unified LLM API proxy and router

## References

- <https://docs.livekit.io/home/>
- <https://docs.livekit.io/agents/>
