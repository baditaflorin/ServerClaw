# ADR 0285: Whisper ASR As The CPU Speech-To-Text Service

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

The platform can produce voice output via Piper TTS (ADR 0284), but has no
corresponding voice input path. Audio arriving from operator voice sessions,
recorded meeting uploads, or voice messages in Mattermost has nowhere to go
for transcription.

Closing the voice loop requires a speech-to-text service that:

- accepts audio in common formats (WAV, MP3, WebM, OGG)
- returns a text transcript the agent pipeline can consume
- runs on CPU without a GPU dependency
- is accurate enough at conversational and operator-instruction quality

OpenAI Whisper models are the open-source standard for high-accuracy
multilingual transcription. The `tiny` and `base` quantized models run at
real-time or faster on a modern CPU core. `whisper-asr-webservice` wraps the
faster-whisper CPU backend behind a REST/OpenAI-compatible API endpoint.

The faster-whisper backend uses CTranslate2 int8 quantization, which gives
3–5× throughput improvement over the original PyTorch implementation on CPU
with no accuracy loss at `base` model size.

## Decision

We will deploy **whisper-asr-webservice** (faster-whisper backend) as the
CPU speech-to-text service.

### Deployment rules

- the service runs as a Docker Compose service on the docker-runtime VM
- the default model is `base` (English or multilingual); the model is declared
  in the Ansible role defaults and downloaded on first container start
- the service exposes the `/asr` endpoint (OpenAI-compatible `/v1/audio/transcriptions`
  is also available) on the guest network
- the service is internal-only; no public subdomain is issued
- no secrets are required

### API contract

- callers POST an audio file to `/asr` or `/v1/audio/transcriptions` and
  receive a JSON transcript
- language detection is automatic; callers may pass a `language` hint to
  improve accuracy on known-language audio
- the service processes one request at a time per worker; concurrent
  transcription requires multiple service replicas if needed

### Consumer conventions

- ServerClaw voice sessions pipe incoming audio from a Livekit room
  (ADR 0293) through Whisper ASR before feeding the transcript to the LLM
- Windmill workflows that accept audio uploads use Whisper ASR to produce
  a text transcript as the first pipeline step
- n8n voice-message integrations route audio through Whisper ASR before
  passing text to downstream automation steps

## Consequences

**Positive**

- Voice input becomes a first-class pipeline step across all automation layers
  without any GPU requirement.
- The OpenAI-compatible API surface means any code already using the OpenAI
  transcription API can point at this service with a base URL change.
- `base` model accuracy is sufficient for operator commands and conversational
  input; `small` can be substituted in the Ansible role if higher accuracy is
  needed at acceptable latency cost.
- CPU-only operation means the service can run continuously on the same VM
  as other services without GPU scheduling concerns.

**Negative / Trade-offs**

- `base` model transcription at real-time speed consumes approximately one
  full CPU core while processing; long audio files block that core for the
  duration.
- Accuracy on heavily accented or technical-vocabulary speech may require
  upgrading to the `small` model at the cost of 2–3× higher CPU use.

## Boundaries

- Whisper ASR is the transcription service only; it does not perform speaker
  diarisation, language translation, or intent classification.
- Whisper ASR does not replace Loki for log-based text ingestion or Tika for
  document text extraction; it handles audio input exclusively.
- Whisper ASR is not used for real-time streaming transcription at launch;
  it processes complete audio files submitted as HTTP requests.

## Related ADRs

- ADR 0254: ServerClaw as a distinct self-hosted agent product on LV3
- ADR 0275: Apache Tika Server for document text extraction in the RAG pipeline
- ADR 0284: Piper TTS as the CPU neural text-to-speech service
- ADR 0293: Livekit as the real-time audio and voice channel for agents

## References

- <https://github.com/ahmetoner/whisper-asr-webservice>
- <https://github.com/SYSTRAN/faster-whisper>
