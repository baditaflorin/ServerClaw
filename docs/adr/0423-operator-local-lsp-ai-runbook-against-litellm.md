# ADR 0423: Operator-Local lsp-ai Against LiteLLM — Runbook and Model Alias

- Status: Rejected
- Rejected In Favour Of: ADR 0422 (do not deploy lsp-ai in any form)
- Implementation Status: Not Implemented — will not be implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Implemented On: N/A
- Date: 2026-04-21
- Concern: Developer Experience, Documentation, Model Catalog
- Depends on: ADR 0422 (lsp-ai evaluation), ADR 0145 (Ollama), ADR 0287 (LiteLLM)
- Tags: lsp-ai, runbook, operator, fim, ollama, litellm, documentation, rejected

---

## Status Note — 2026-04-21

This ADR was drafted alongside ADR 0422 as the "Option B" follow-through:
adding a FIM model to the Ollama catalog, a LiteLLM alias, and a
per-operator install runbook. After review, ADR 0422 was accepted as a
**decision-only record** with no deployment in any form, including this
operator-local path.

This ADR is kept in the repo as `Rejected` rather than deleted because
the design work (model alias, runbook scope, observability wiring,
rollback plan) is the argument for and against the operator-local path
in one place. A future ADR that wants to revisit the decision can
reference this document directly instead of re-deriving the scope.

**No artefacts described below are to be created.** This is a historical
design document, not an implementation plan.

---

---

## Context

ADR 0422 rejected hosting lsp-ai as a platform service and recommended an
**operator-local** deployment path for operators on LSP-native editors
(Neovim, Helix, pure Emacs, Sublime) that lack a strong AI-plugin
ecosystem. This ADR delivers the minimum platform-side changes required
to make that path first-class and discoverable, without introducing an
Ansible role, a compose file, or a catalog entry for lsp-ai itself.

The platform owes operators three things before they can self-serve an
lsp-ai install:

1. **A FIM-capable completion model** reachable through the existing
   Ollama surface. Today's Ollama catalog pins `llama3.2:3b` — a small
   instruction model fit for the goal-compiler fallback, but not tuned
   for code infill. Without a code-completion model, routing editor FIM
   requests to Ollama produces poor suggestions.
2. **A LiteLLM alias** for that model so operators can point lsp-ai at a
   stable name (`code-completion-local`) rather than a raw Ollama model
   ID. This keeps Langfuse observability wired through the existing
   LiteLLM callback and keeps per-consumer budgeting enforceable.
3. **A runbook** showing how to install the lsp-ai binary, configure it
   for Neovim and Helix, authenticate to LiteLLM with a personal token,
   and verify the integration end-to-end.

Nothing in this ADR creates a platform service for lsp-ai. The binary
is installed per-operator; the editor configuration lives in the
operator's dotfiles; the credential is a personal API token under the
identity model (ADR 0046).

---

## Decision

Add the three artefacts below to the repo.

### 1. Extend the Ollama model catalog with a code-completion model

File: `config/ollama-models.yaml`

Add a FIM-capable model entry (exact choice left to the implementer;
recommended default: `qwen2.5-coder:7b` for a 7B/Q4 fit within existing
`docker-runtime` RAM, or `qwen2.5-coder:1.5b` for CPU-only deployments).
The model is declared with `startup: false` so it is pulled lazily on
first use and does not slow convergence.

```yaml
# excerpt — not the full file
models:
  - id: qwen2.5-coder:7b
    purpose: code-completion
    fim: true
    startup: false
    notes: >-
      Code-tuned fill-in-middle model for operator-local lsp-ai clients
      (ADR 0423). Not consumed by the goal compiler or any server-side
      platform component.
```

No change to `ollama_runtime` role code is required — the catalog is
already the declarative source.

### 2. Declare the LiteLLM alias

File: the LiteLLM config template inside `roles/litellm_runtime`.

Add one entry:

```yaml
- model_name: code-completion-local
  litellm_params:
    model: ollama/qwen2.5-coder:7b
    api_base: http://ollama.lv3.internal:11434
  model_info:
    capability_tags: [coding, fim]
    consumer: operator-lsp-ai
```

The alias routes through the existing Langfuse callback, the existing
per-consumer budget table, and the existing `/metrics` scrape, so there
is no new observability wiring.

### 3. Publish the operator runbook

File: `docs/runbooks/operator-lsp-ai.md`

Required sections:

- **Install** — `cargo install lsp-ai`, or platform-packaged binaries if
  available; pinned minimum version.
- **Personal LiteLLM token** — point operators at the existing account
  provisioning API (ADR 0411) to issue a scoped token with budget
  `operator-lsp-ai`.
- **Neovim config** — minimal `nvim-lspconfig` snippet wiring lsp-ai as
  an attached LSP client with the `code-completion-local` backend and
  the operator's token.
- **Helix config** — equivalent `languages.toml` and `config.toml`
  snippets.
- **Verification** — open a file, confirm completion suggestions arrive;
  confirm the call appears in Langfuse under trace tag
  `consumer=operator-lsp-ai`.
- **Privacy note** — every FIM prompt (which includes the surrounding
  code buffer) is logged by Langfuse. Operators who do not want this
  must configure lsp-ai to redact or disable the callback, and should
  not route through LiteLLM in that case.
- **Offline fallback** — a section documenting a direct-to-Ollama
  config for operators on the private network who explicitly opt out
  of central observability. This path bypasses LiteLLM's budget
  controls and is discouraged for day-to-day use.
- **Support boundary** — the runbook states that lsp-ai itself is
  not a platform-supported service; issues with the binary go
  upstream. The platform supports the **endpoint** (LiteLLM alias)
  and the **model** (Ollama catalog entry).

### 4. Explicitly do not add

- No `roles/lsp_ai_runtime` and no playbook.
- No entry in `catalog/` (service, dependency-graph, capability,
  command, workflow, image, secret, health-probe catalogs).
- No DNS record, no Nginx site config, no Keycloak OIDC client.
- No `versions/stack.yaml` receipt for lsp-ai.
- No workstream template that treats lsp-ai as a platform deliverable
  beyond the three files above.

If any of those surfaces sprout an lsp-ai reference, the pre-push gate
should flag it and the reviewer should re-read ADR 0422 before merging.

---

## Consequences

**Positive**

- Operators on Neovim, Helix, Emacs, and Sublime get a supported
  inline-completion path with a one-page runbook and no per-operator
  negotiation.
- Every FIM prompt is observable in Langfuse and billable against an
  existing per-consumer budget by default.
- The model alias is a clean seam: future swaps (e.g. to a GPU-hosted
  `deepseek-coder-v3` on `runtime-ai`) are a LiteLLM config edit and
  do not touch operator configs.
- Claude Code remains the primary conversational interface; this ADR
  deliberately does not compete with it.

**Negative / Trade-offs**

- One additional Ollama model on `docker-runtime` consumes ~4–8 GB of
  disk and, when loaded, RAM. Acceptable within current
  `docker-runtime` envelope.
- lsp-ai is upstream-maintained but feature-complete; a critical bug
  may require an internal fork. Platform support is scoped to the
  endpoint and the model, not the client binary.
- Operators may mis-configure lsp-ai to call Ollama directly, bypassing
  Langfuse. The runbook warns against this but cannot enforce it
  without a firewall change, which is out of scope here.
- Introduces a second "supported" editor AI path alongside Claude Code.
  Documentation must keep the boundary clear: Claude Code for
  conversational / multi-file / tool-calling work; lsp-ai for inline
  FIM completion inside LSP-native editors only.

## Boundaries

- This ADR does not authorise a GPU deployment, a dedicated VM for
  code-completion inference, or a public edge endpoint for the
  completion model.
- This ADR does not change Claude Code's role in the platform.
- This ADR does not mandate operator adoption. Operators on editors
  with strong native AI plugins (Continue.dev, avante.nvim, Zed AI,
  Cursor) should keep using those plugins pointed directly at the
  LiteLLM alias; lsp-ai is not the recommended path for them.

## Rollback

- Remove the `qwen2.5-coder` entry from `config/ollama-models.yaml`
  and the `code-completion-local` alias from the LiteLLM config.
- Archive `docs/runbooks/operator-lsp-ai.md` with a deprecation header.
- Rotate any issued LiteLLM tokens tagged `operator-lsp-ai`.

No stateful data is written on behalf of lsp-ai, so rollback is
idempotent and does not require a migration.

## Related ADRs

- ADR 0046: Identity classes for humans, services, and agents
- ADR 0095: API gateway as the unified platform entry point
- ADR 0145: Ollama for local LLM inference
- ADR 0146: Langfuse for agent observability
- ADR 0287: LiteLLM as the unified LLM API proxy and router
- ADR 0411: Unified account provisioning API
- ADR 0422: Evaluate lsp-ai as an editor-side AI language server (companion)

## References

- <https://github.com/SilasMarvin/lsp-ai>
- <https://ollama.com/library/qwen2.5-coder>
- <https://docs.litellm.ai/docs/proxy/configs>
