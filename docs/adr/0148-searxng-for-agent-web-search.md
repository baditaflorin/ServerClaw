# ADR 0148: SearXNG for Agent Web Search

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.175.0
- Implemented In Platform Version: 0.130.21
- Implemented On: 2026-03-26
- Date: 2026-03-24

## Context

Agent workflows (triage engine, Claude Code sessions, Open WebUI) occasionally need to search the web for:

- Querying for CVE details when a dependency vulnerability is detected.
- Looking up documentation for an unfamiliar Ansible module or Docker parameter.
- Checking whether a known error message is a recognised bug in an upstream project.
- Researching whether a new platform tool (proposed in an ADR) has known security issues.

Currently these searches are done by:
- The operator performing a manual Google search and pasting results into a Claude Code session.
- Open WebUI using a web search tool that sends queries to Google or Bing with the operator's IP address and query history.
- Agent prompts that ask Claude to use its training knowledge (which may be stale).

The problems:
- **Privacy**: sending operator queries about internal infrastructure issues to Google exposes query content (e.g., "proxmox backup failed error 502 after keycloak update") that reveals internal state.
- **Personalisation**: Google's results are personalised; a self-hosted agent may get different results than an operator.
- **Rate limiting**: automated queries to Google without an API key are rate-limited and may trigger CAPTCHAs.
- **Dependency**: agent workflows that depend on external search APIs have an external availability dependency.

**SearXNG** is a self-hosted, open-source metasearch engine that aggregates results from multiple search engines (Google, Bing, DuckDuckGo, etc.) without tracking or personalisation. It provides a REST API (`/search?q=...&format=json`) that agents can query directly.

## Decision

We will deploy **SearXNG** on `docker-runtime` as a self-hosted search aggregation API for agent and operator use.

### Deployment

```yaml
# In versions/stack.yaml
- service: searxng
  vm: docker-runtime
  image: searxng/searxng:latest
  port: 8881
  access: internal_only     # Accessible on the private network; not Tailscale-only (agents use it)
  config_volume: /data/searxng
  subdomain: search.example.com # Tailscale-only; not public
```

SearXNG uses outbound connections to external search engines but never exposes the query source IP as a user identifier: from Google's perspective, SearXNG is a search aggregator, not an individual operator.

### SearXNG configuration

```yaml
# config/searxng/settings.yml (managed by Ansible)
use_default_settings: true

server:
  secret_key: "{{ vault_searxng_secret }}"
  bind_address: "0.0.0.0:8881"
  base_url: "https://search.example.com"

search:
  safe_search: 0
  default_lang: "en"
  formats: ["html", "json"]  # JSON format enables API use by agents

engines:
  - name: google
    engine: google
    weight: 2
  - name: bing
    engine: bing
    weight: 1
  - name: duckduckgo
    engine: duckduckgo
    weight: 1
  - name: github
    engine: github          # Important for source code and issue searching
    weight: 2
  - name: stackoverflow
    engine: stackoverflow
    weight: 2
```

### Agent API usage

```python
# platform/web/search.py

class WebSearchClient:
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        response = requests.get(
            "http://searxng:8881/search",
            params={"q": query, "format": "json", "results": max_results},
            timeout=10,
        )
        return [
            SearchResult(title=r["title"], url=r["url"], content=r.get("content", ""))
            for r in response.json()["results"]
        ]
```

### Integration with Open WebUI

Open WebUI (ADR 0060) supports custom search engines via its RAG web search configuration. SearXNG is registered as the default web search provider:

```yaml
# Open WebUI environment
RAG_WEB_SEARCH_ENGINE: "searxng"
SEARXNG_QUERY_URL: "http://searxng:8881/search?q=<query>"
```

This means that when an operator asks Open WebUI's chat interface to "search the web for...", the query goes to the local SearXNG instance rather than to a tracked external API.

### Triage engine integration

The triage engine (ADR 0114) can use SearXNG to look up CVE details or known error messages when no matching case is found in the case library:

```python
# In triage engine, after case library search returns no match
if not case_library_results and signal.error_message:
    web_results = web_search.search(
        f'site:github.com OR site:stackoverflow.com "{signal.error_message[:100]}"',
        max_results=3,
    )
    if web_results:
        triage_report["web_search_references"] = [r.url for r in web_results]
```

Web search results in a triage report are links only; the content is not summarised by an LLM automatically (to avoid token cost and hallucination risk for production triage). The operator can follow the links.

## Implementation Notes

- The repository implementation lives in `playbooks/searxng.yml`,
  `collections/ansible_collections/lv3/platform/roles/searxng_runtime/`,
  `platform/web/search.py`, and the related catalog and inventory entries.
- Open WebUI is now rendered with the repo-managed SearXNG integration flags and
  `SEARXNG_QUERY_URL` so web search stays on the private platform path.
- The repo-side client defaults to the tailnet hostname
  `http://search.example.com/search?q=<query>&format=json` and adds the `results`
  parameter itself when the caller does not supply one.
- The SearXNG runtime now manages both `settings.yml` and `limiter.toml`. The
  private platform ranges (`10.10.10.0/24`, `172.16.0.0/12`, `192.168.0.0/16`,
  `100.64.0.0/10`) are passlisted so the JSON API works for tailnet and
  Docker-local callers without tripping SearXNG's upstream bot-detection
  defaults.
- The runtime role now recreates the SearXNG container when managed config
  files change so mounted config updates are applied live, not just written to
  disk.
- The live platform rollout completed on 2026-03-26 from the workstream branch:
  the guest runtime serves `http://10.10.10.20:8881/search?...&format=json`,
  the Proxmox host Tailscale proxy serves the same API at
  `http://100.64.0.1/search?...`, `search.example.com` resolves to `100.64.0.1`,
  and the hostname-backed JSON endpoint returns results.
- The final DNS publication had to be retried after `13:00 UTC` on
  2026-03-26 because Hetzner's legacy `dns.hetzner.com` write API was in a
  scheduled brownout window and returned `503` for record creation at
  `12:53 UTC`.

### Rate limiting and caching

SearXNG includes built-in rate limiting (Redis-backed). A 5-second per-query rate limit prevents agent loops from exhausting the upstream search engine rate limits. Results are cached for 60 seconds to avoid duplicate requests for the same query within a short window.

## Consequences

**Positive**

- Agent and operator web searches no longer leak query content to Google with the operator's IP address.
- Agents can perform web searches as part of automated workflows (triage, runbook research) without external API keys or rate-limit concerns from the upstream providers.
- Open WebUI web search becomes private and reliable.

**Negative / Trade-offs**

- SearXNG's search quality depends on aggregating external search engine results. If upstream engines return poor results for the specific domain vocabulary of the platform (infrastructure, Proxmox, Ansible), the local search may be less useful than a direct Google search with personalisation.
- SearXNG has outbound connectivity to multiple external search engines. From a privacy perspective, the query is not sent from the operator's IP directly, but SearXNG's server IP is still making the search request. An adversary with access to search engine logs could potentially correlate queries from the SearXNG IP with platform activity.
- Result freshness depends on SearXNG's caching and the upstream engine's indexing. For breaking CVEs published in the last hour, SearXNG may return stale results.

## Boundaries

- SearXNG is for general web search. Internal platform search (ADRs, runbooks, cases) continues to use the local search fabric (ADR 0121).
- SearXNG results are links and snippets only. Agents are responsible for fetching and interpreting page content if needed; SearXNG does not crawl or index pages beyond what search engines return.

## Related ADRs

- ADR 0060: Open WebUI (web search integration)
- ADR 0114: Rule-based incident triage engine (web search for novel error messages)
- ADR 0121: Local search and indexing fabric (internal search; not replaced by SearXNG)
- ADR 0125: Agent capability bounds (web search is a permitted read surface for T2+ agents)
- ADR 0145: Ollama (agents may combine web search results with local LLM summarisation)
