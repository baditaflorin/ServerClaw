# ADR 0422: Evaluate lsp-ai as an Editor-Side AI Language Server

- Status: Accepted
- Implementation Status: Decision Only — No Deployment
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Implemented On: 2026-04-21
- Date: 2026-04-21
- Concern: Developer Experience, Agent Discovery, Platform Integration
- Depends on: ADR 0145 (Ollama), ADR 0287 (LiteLLM), ADR 0394 (LibreChat Agents API)
- Tags: lsp-ai, lsp, ide, editor, coding-assistant, fim, evaluation, do-not-deploy
- Upstream: <https://github.com/SilasMarvin/lsp-ai>

---

## Context

[lsp-ai](https://github.com/SilasMarvin/lsp-ai) is an MIT-licensed language
server written in Rust that implements the Language Server Protocol to expose
AI-backed code completion, in-editor chat, and user-defined "custom actions"
(refactors, generators) to any LSP-capable editor (VS Code, Neovim, Emacs,
Helix, Sublime, Zed). Supported backends include llama.cpp, **Ollama**,
OpenAI-compatible APIs, Anthropic, Gemini, and Mistral FIM endpoints. The
upstream project is feature-complete and receives maintenance but no new
features.

The platform already stands up every backend lsp-ai can talk to:

| Capability lsp-ai needs | Platform surface | ADR |
|---|---|---|
| Local inference (Ollama API, FIM-capable models) | `ollama_runtime` on `docker-runtime`, port `11434` | 0145 |
| OpenAI-compatible proxy with routing, retries, fallback, cost tracking | `litellm_runtime` on `docker-runtime` | 0287 |
| Observability of every LLM call (traces, token cost, latency) | Langfuse callback wired to LiteLLM | 0146 |
| Conversational agents over tool chains | LibreChat Agents API | 0394 |

The platform's primary AI developer interface is Claude Code
(see [README](../../README.md) "AI-Native Infrastructure"). Every ADR,
runbook, and workstream is written so a Claude Code session can read and
execute it. The platform does not manage developer workstations and has no
ADR governing editor-side AI tooling.

### Why evaluate lsp-ai now

1. Some operators prefer modal editors (Neovim, Helix) or lightweight editors
   (Sublime, Emacs) whose AI-plugin ecosystems are narrower than the VS Code
   / Cursor stack that Claude Code ships into. A single LSP shim would let
   those editors inherit FIM completion and inline chat without per-editor
   plugins.
2. Routing every developer keystroke through the platform's LiteLLM endpoint
   (instead of external SaaS APIs like GitHub Copilot or Cursor Cloud) would
   keep request telemetry visible in Langfuse and costs bounded by the
   per-consumer budgets already configured there.
3. Ollama already hosts a FIM-capable model surface for the goal compiler;
   adding one completion-tuned model (e.g. `qwen2.5-coder:7b`) would
   extend that surface without changing the runtime shape.
4. The `runtime-ai` VM is declared in topology but currently only runs
   Ollama for CPU inference. If an editor-side assistant becomes a
   first-class use case, it motivates (but does not require) GPU rollout
   on that VM.

### What lsp-ai would NOT change

- Claude Code remains the conversational, multi-file, tool-calling interface.
  lsp-ai operates at the single-file, cursor-position granularity: FIM
  completion, selection rewrite, explain-this-function. The two are
  complementary, not competing.
- No new backend is introduced. lsp-ai consumes existing Ollama or LiteLLM
  endpoints.
- No editor is mandated. lsp-ai is opt-in per operator, per editor.

### Architectural constraint: LSP is stdio

LSP is a stdio protocol. A "language server" is a subprocess the editor
spawns on demand; it does not run as a long-lived network service. Despite
wording in lsp-ai's README about being a "server-side tool", the binary
must run on the same machine as (or at least as a child process of) the
editor. This platform does not host developer workstations, so lsp-ai
cannot be "deployed" the way Ollama or LibreChat is. The only platform
surface lsp-ai would consume is the existing HTTP LLM endpoint.

This constraint has three consequences for this ADR:

1. There is no `lsp_ai_runtime` Ansible role to write. There is no
   playbook, no compose file, no Nginx fragment, no Keycloak client.
2. All the platform owes is: a **documented, authenticated HTTP endpoint**
   for LLM requests (already provided by LiteLLM via the API gateway),
   and **a documented FIM-capable model alias** (adding one to the Ollama
   catalog).
3. Distribution and installation of the lsp-ai binary, editor plugin
   configuration, and per-operator credentials live in the operator's
   personal dotfiles or `.local/` overlay, not in the generic repo.

---

## Options Considered

### Option A — Host lsp-ai as a platform service

Build `lsp_ai_runtime`, expose it behind the API gateway, share a single
instance across all operators.

Rejected because LSP is stdio: there is nothing to "share". A centrally
hosted lsp-ai process cannot be driven by a remote editor — the editor
would need a local lsp-ai process in any case. Building infrastructure
for this would be ceremony around a binary that each operator already
runs on their own laptop.

### Option B — Operator-local binary, pointed at the platform's LiteLLM endpoint

Each operator installs the lsp-ai binary through their OS package manager
or `cargo install`, configures their editor to spawn it, and points its
backend config at `https://api.example.com/v1/litellm/...` with a
personal API token issued through the existing identity model (ADR 0046).
The platform ships a runbook and a sample lsp-ai config; nothing more.

This is the only architecturally coherent option. It is detailed in the
companion ADR (0423).

### Option C — Do nothing; recommend Continue.dev / avante.nvim / Zed AI / Cody

Modern editor-native AI plugins (Continue.dev, avante.nvim, codecompanion.nvim,
Zed's built-in assistant, Cursor, Cody) all accept an OpenAI-compatible
`base_url` and can point at LiteLLM directly without lsp-ai in the middle.
For VS Code / JetBrains / Cursor / Zed users, this path is simpler and
better-supported upstream than lsp-ai.

This option is the *default* for operators using those editors and should
be documented alongside Option B.

### Option D — Rely solely on Claude Code

Drop the evaluation; Claude Code covers the coding-assistant need for the
primary workflow. Editor-native inline completion is out of scope for
the platform.

This is the status quo and is defensible, but leaves operators on editors
with limited AI-plugin ecosystems (Helix, Sublime, pure Emacs without
`gptel` / `ellama`) without a supported path.

---

## Decision

**Do not deploy lsp-ai in any form.** Options A, B, C, and D were
considered; after review, the platform accepts Option D (status quo —
Claude Code remains the primary developer-AI interface, editor-native
plugins are the recommended path for operators who want inline assist,
and no platform artefacts are added for lsp-ai).

This ADR is filed as a **decision-only record** so that future sessions
find the evaluation and do not re-open it without new evidence. Nothing
in the repo changes as a result of this ADR — no Ollama catalog edits,
no LiteLLM alias, no runbook, no role, no playbook, no receipt.

### Why not even the operator-local path (Option B)

The companion proposal in ADR 0423 (operator-local install pointed at
LiteLLM) is coherent and low-cost, but:

1. It introduces a second "supported" editor-AI path alongside Claude
   Code, and documentation cost to keep the boundary clear exceeds the
   benefit for the current operator set.
2. The only capability gap lsp-ai fills (inline FIM for LSP-only
   editors) is real but narrow, and operators on those editors already
   have working paths — `gptel` / `ellama` for Emacs, `avante.nvim` /
   `codecompanion.nvim` for Neovim, Helix's experimental AI branches —
   all of which accept an OpenAI-compatible base URL and can point
   directly at LiteLLM without an LSP shim in the middle.
3. Any operator who wants lsp-ai specifically can still install it
   locally and point it at the existing LiteLLM endpoint with a
   personal token — that path is not blocked, it is simply not
   platform-supported and not documented in a runbook. If demand grows
   later, this decision can be revisited with a new ADR.

### What this decision explicitly prohibits

- No `roles/lsp_ai_runtime`, no playbook, no compose file.
- No entry in `catalog/`, `inventory/group_vars/`, platform manifest,
  dependency graph, or health probes.
- No DNS record, Nginx fragment, Keycloak OIDC client, or
  `versions/stack.yaml` receipt.
- No runbook under `docs/runbooks/` for lsp-ai install.
- No code-completion-tuned model added to `config/ollama-models.yaml`
  on lsp-ai's behalf. (A future ADR may still add a
  code-completion model for other reasons — e.g. agent tool completion
  — but not driven by lsp-ai.)

If a future change request touches any of the above surfaces with
lsp-ai, the pre-push gate and reviewers should reject it and require a
new ADR that explicitly supersedes this one.

## Redundancy Analysis

lsp-ai is **partially redundant** with existing platform capability:

| lsp-ai feature | Already covered by | Redundant? |
|---|---|---|
| Route editor → Ollama | Direct `OLLAMA_BASE_URL` env on any editor plugin | Yes (but lsp-ai normalises across editors) |
| Route editor → OpenAI-compatible | LiteLLM `/v1/chat/completions` + any editor plugin | Yes |
| In-editor chat | Claude Code, LibreChat UI, avante.nvim, Continue.dev | Yes — duplicates Claude Code's primary surface |
| Inline FIM completion | **Not covered** by Claude Code (which is conversational) | No — this is the one gap lsp-ai fills for LSP-only editors |
| Custom code actions | Claude Code slash commands, aider, editor snippets | Yes |
| Observability of AI calls | Langfuse (wired to LiteLLM) | Yes — provided the operator points lsp-ai at LiteLLM, not a raw Ollama port |

The only capability gap lsp-ai fills is **inline FIM completion for
operators using LSP-native editors whose AI-plugin ecosystem is weak**.
Everything else duplicates existing platform surfaces.

---

## Consequences

**Positive (of not deploying)**

- Zero new surface area: no role, no playbook, no catalog entry, no
  Keycloak client, no Nginx fragment, no health probe, no receipt, no
  addition to the cross-catalog validator's working set.
- No new operator-support burden. Claude Code remains the single
  documented path for AI-assisted development on the platform.
- No duplicated observability wiring, no second "supported" editor-AI
  path to keep in sync with the first.
- The evaluation is preserved in the repo as an ADR so future sessions
  can read the reasoning without re-deriving it.

**Negative / Trade-offs**

- Operators on LSP-only editors with weak AI-plugin ecosystems (Helix,
  Sublime, pure Emacs without `gptel` / `ellama`) do not get a
  platform-blessed inline-completion path. They can still install
  lsp-ai themselves against the existing LiteLLM endpoint, but without
  a runbook or platform support.
- If demand for editor-side FIM grows materially, this decision will
  need to be revisited — the evaluation work does not have to be
  redone, but the deployment decision does.

**Revisit triggers**

Re-open this ADR with new evidence if any of the following change:

- Multiple operators independently ask for platform support for
  editor-side FIM completion.
- Claude Code's inline-completion ergonomics regress or are withdrawn.
- A code-completion model is added to the Ollama catalog for another
  reason (agent tool completion, internal tooling), making the
  marginal cost of enabling lsp-ai effectively zero.
- lsp-ai ships a mode that cannot be replicated by pointing a
  native editor plugin at LiteLLM.

## Boundaries

- This ADR is scoped to evaluation. The "do not host" decision is
  recorded here but the operator-local runbook, model alias, and
  LiteLLM config deltas are delivered by ADR 0423.
- lsp-ai does not replace Claude Code, LibreChat, Dify, or any
  server-side agent interface. It is an inline-completion shim for
  editors that cannot reach the platform AI stack through a native
  plugin.
- Any proposal to host lsp-ai centrally, add it to the service catalog,
  or give it a public edge publication is **explicitly out of scope**
  and would require a new ADR overriding this one.

## Related ADRs

- ADR 0095: API gateway as the unified platform entry point
- ADR 0145: Ollama for local LLM inference
- ADR 0146: Langfuse for agent observability
- ADR 0287: LiteLLM as the unified LLM API proxy and router
- ADR 0394: LibreChat Agents API integration
- ADR 0395: Agent interface abstraction layer
- ADR 0407: Generic-by-default local overlay architecture
- ADR 0423: Operator-local runbook for lsp-ai against LiteLLM (companion)

## References

- <https://github.com/SilasMarvin/lsp-ai>
- <https://microsoft.github.io/language-server-protocol/>
