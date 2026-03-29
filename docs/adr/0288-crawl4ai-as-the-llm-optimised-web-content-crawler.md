# ADR 0288: Crawl4AI As The LLM-Optimised Web Content Crawler

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

The platform's RAG context service (ADR 0198) and ServerClaw memory substrate
(ADR 0263) are fed by structured document uploads. They have no mechanism for
autonomously harvesting content from URLs at agent or workflow request time.

Two existing services touch the web but serve different purposes:

- **SearXNG** (ADR 0148) performs meta-search and returns result links; it
  does not fetch or clean the linked content
- **Changedetection.io** (ADR 0280) monitors pages for changes; it does not
  extract clean, LLM-ready content

When an agent or Windmill workflow needs to ingest a web page, documentation
site, or public API response into the RAG pipeline today, the operator must
manually download the content and upload it as a file. There is no autonomous
fetch-and-ingest path.

Crawl4AI is a CPU-only async web crawling service purpose-built for LLM
consumption. Unlike general-purpose scrapers, it applies a cleaning pipeline
that produces Markdown output stripped of navigation chrome, cookie banners,
and irrelevant boilerplate, leaving only the substantive page content. It
supports JavaScript-rendered pages via a bundled headless browser option and
structured extraction via CSS selector or LLM-guided schemas.

## Decision

We will deploy **Crawl4AI** as the LLM-optimised web content crawler.

### Deployment rules

- Crawl4AI runs as a Docker Compose service on the docker-runtime VM exposing
  a REST API
- it is internal-only; no public subdomain is issued
- the service is stateless; crawl results are returned synchronously in the
  HTTP response or pushed to the NATS event bus (ADR 0276) for async
  ingestion pipelines
- no secrets are required for public URL crawling; authenticated crawl targets
  pass credentials via the API request body, stored in OpenBao by the caller

### Crawl contract

- callers POST a URL and optional extraction schema; Crawl4AI returns clean
  Markdown content and metadata (title, author, canonical URL, crawl timestamp)
- the RAG ingestion pipeline treats Crawl4AI output as a virtual document
  upload: it flows through Tika (ADR 0275) for MIME confirmation, is staged
  to MinIO (ADR 0274), and is embedded into Qdrant
- extraction schemas allow structured JSON output (e.g. extracting product
  names from a pricing page) in addition to Markdown; schema definitions are
  caller-owned

### Autonomous agent usage

- ServerClaw agents may call the Crawl4AI endpoint as a tool to fetch and
  ingest referenced URLs on demand during a session
- Windmill workflows use Crawl4AI to harvest documentation pages, changelog
  feeds, and external knowledge sources on a schedule
- crawled content is tagged with `source: crawl4ai` and the originating URL
  in the RAG provenance record for citation and freshness tracking

## Consequences

**Positive**

- Agents become self-sufficient for web research without manual operator
  upload steps; any public URL becomes a potential RAG source on demand.
- Clean Markdown output reduces tokenisation noise compared to raw HTML,
  improving embedding quality and LLM comprehension.
- Async delivery via NATS means crawl requests do not block the calling agent;
  content arrives in the RAG index when ready.
- CPU-only async operation scales to many concurrent crawl requests without
  GPU or heavyweight infra.

**Negative / Trade-offs**

- Crawling external sites at high frequency or without rate limiting may
  trigger bot-detection or violate site terms of service; the platform must
  enforce per-domain crawl rate limits.
- JavaScript-rendered pages require the headless browser mode which consumes
  significantly more CPU and memory than the plain HTTP mode; those targets
  should be explicitly flagged.

## Boundaries

- Crawl4AI fetches and cleans web content; it does not replace SearXNG for
  discovering what to crawl.
- Crawl4AI does not replace Changedetection.io for change-signal monitoring;
  it is used to harvest content, not to watch for differences.
- Crawl4AI does not store crawl history; provenance tracking is the
  responsibility of the RAG ingestion pipeline.
- Crawl4AI is not a link graph spider; it fetches single pages or shallow
  page sets, not full-site recursive crawls.

## Related ADRs

- ADR 0148: SearXNG for private web search
- ADR 0198: Qdrant vector search for semantic platform RAG
- ADR 0254: ServerClaw as a distinct self-hosted agent product on LV3
- ADR 0274: MinIO as the S3-compatible object storage layer
- ADR 0275: Apache Tika Server for document text extraction in the RAG pipeline
- ADR 0276: NATS JetStream as the platform event bus
- ADR 0280: Changedetection.io for external content and API change monitoring

## References

- <https://crawl4ai.com/mkdocs/>
