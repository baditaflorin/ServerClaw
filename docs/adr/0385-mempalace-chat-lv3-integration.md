# ADR 0385: MemPalace Integration with chat.lv3.org

- **Status:** Proposed
- **Implementation Status:** Design Phase
- **Date:** 2026-04-09
- **Author:** Claude Agent
- **Related:** ADR 0384 (MemPalace Agent Memory System Integration)

## Context

Following ADR 0384, MemPalace is now integrated with Claude Code for cross-session memory (737 indexed memories, 3 specialist agents, auto-save hooks).

The platform also operates **chat.lv3.org**, a self-hosted AI chat service. Currently:
- chat.lv3.org operates as an isolated service without persistent cross-session memory
- Users can access both Claude Code (Claude.app) and chat.lv3.org
- Sessions in chat.lv3.org start fresh each time (no memory of prior conversations)
- Decision context and debugging insights from chat.lv3.org are not available to Claude Code, and vice versa

### Current State

```
Claude Code (Claude.app)          chat.lv3.org (Browser/API)
     │                                    │
     ├─→ MemPalace palace                 └─→ No persistent memory
     │   (737 memories)                       (stateless sessions)
     │
     └─ Isolated from chat.lv3.org
```

### Problem

1. **Fragmented Knowledge** — Decisions made in chat.lv3.org aren't available to Claude Code agents
2. **Duplicate Work** — Same questions asked in both interfaces start from scratch
3. **Missing Context** — Infrastructure decisions discussed in chat.lv3.org aren't indexed for future use
4. **Asymmetric Memory** — Claude Code remembers (MemPalace), chat.lv3.org forgets

## Decision

Implement **unified cross-interface memory** by connecting chat.lv3.org to MemPalace, enabling both Claude Code and chat.lv3.org users to access a shared memory pool.

### Integration Architecture

**Option A: MCP Server (Recommended for native integration)**

```
chat.lv3.org  ──┐
                ├──→ MemPalace MCP Server ──→ ~/.mempalace/palace
                │    (19 standard tools)        (shared memory pool)
Claude Code   ──┘
```

**Advantages:**
- Leverages MemPalace's 19 built-in MCP tools
- Native integration with AI models via MCP protocol
- chat.lv3.org can use `mempalace_search`, `mempalace_add_drawer`, etc.
- Single unified memory model

**Implementation:**
```bash
# Start MemPalace MCP server (can run as systemd service on platform)
python3 -m mempalace.mcp_server

# chat.lv3.org configures MCP server connection
# Both Claude Code + chat.lv3.org can now access tools
```

---

**Option B: HTTP API Wrapper (For services without MCP support)**

```
chat.lv3.org
    │
    └──→ HTTP API Wrapper ──┐
         (Flask/FastAPI)     │
         /api/search         │
         /api/save           ├──→ MemPalace Python SDK ──→ ~/mempalace/palace
         /api/query          │
         /api/agents         │
         /api/wake-up     ───┘

Claude Code
    │
    └──→ CLI + MCP tools (native)
```

**Advantages:**
- chat.lv3.org just needs HTTP access
- Stateless API (scales horizontally)
- Works with any chat interface

**Implementation:**
```python
# API server (mempalace_api_server.py)
from flask import Flask, jsonify, request
from mempalace.searcher import search_memories
from mempalace.miner import add_drawer
from mempalace.knowledge_graph import KnowledgeGraph

app = Flask(__name__)

@app.post('/api/search')
def search():
    query = request.json['query']
    wing = request.json.get('wing', 'proxmox_florin')
    results = search_memories(query, palace_path="~/.mempalace/palace")
    return jsonify(results)

@app.post('/api/save')
def save_drawer():
    content = request.json['content']
    wing = request.json.get('wing', 'proxmox_florin')
    drawer_id = add_drawer(content, wing=wing, palace_path="~/.mempalace/palace")
    return jsonify({"id": drawer_id})
```

---

**Option C: Webhook + Background Job (For async capturing)**

```
chat.lv3.org (end of session)
    │
    └──→ Trigger webhook ──→ Background job ──→ MemPalace palace
         {
           "session_id": "xyz",
           "messages": [...],
           "summary": "...",
           "decisions": [...]
         }
```

**Advantages:**
- Non-blocking (doesn't slow down chat.lv3.org)
- Can post-process and filter before saving
- Works with existing chat.lv3.org without API changes

**Disadvantages:**
- No real-time access to memories during chat.lv3.org sessions
- Requires extraction/summarization logic
- chat.lv3.org can't call MemPalace mid-session

---

## Recommended Implementation Path

**Phase 1 (This session):** Start with **Option A (MCP Server)** because:
- Simplest to implement (MemPalace already has MCP)
- Most powerful (all 19 tools available)
- chat.lv3.org can use same interface as Claude Code
- Future-proof (works with any MCP-compatible client)

**Steps:**

1. **Run MemPalace MCP Server on platform**
   ```bash
   # Install as systemd service on runtime-control-lv3
   sudo systemctl enable mempalace-mcp-server
   sudo systemctl start mempalace-mcp-server

   # Listen on localhost:5001 or Unix socket
   ```

2. **Configure chat.lv3.org to connect to MCP server**
   ```json
   // chat.lv3.org config
   {
     "mcp_servers": {
       "mempalace": {
         "type": "stdio",
         "command": "python3",
         "args": ["-m", "mempalace.mcp_server"]
       }
     }
   }
   ```

3. **Enable MemPalace tools in chat.lv3.org system prompt**
   ```markdown
   You have access to MemPalace memory system:
   - Use mempalace_search to find past decisions and patterns
   - Use mempalace_add_drawer to save discoveries
   - Use mempalace_wake_up to load critical facts

   See ~mempalace/status for memory structure.
   ```

4. **Test cross-interface memory**
   - Save a memory in chat.lv3.org via `mempalace_add_drawer`
   - Search for it in Claude Code: `python3 -m mempalace search "..."`
   - Verify both can access shared pool

---

## Integration Points

### chat.lv3.org → MemPalace

**Session Start:**
```
User opens chat.lv3.org
  ↓
Load critical facts: mempalace_wake_up
  ↓
Get recent agent discoveries: mempalace_search "today's work"
  ↓
Chat proceeds with context from prior sessions
```

**During Chat:**
```
User: "Why did we choose Postgres over SQLite?"
  ↓
Chat searches: mempalace_search "database decision"
  ↓
Returns: ADR 0359 decision + architect diary insights
```

**Session End:**
```
User's chat complete
  ↓
Webhook triggers: POST /mempalace/save-session
  ↓
Session summary + key decisions saved to mempalace_add_drawer
  ↓
Available to all agents in next session
```

### Memory Model

```
Shared MemPalace Palace (~/.mempalace/palace)
│
├─ wing: proxmox_florin
│  ├─ room: facts (decisions, requirements, scope)
│  ├─ room: events (sessions, milestones, debugging)
│  ├─ room: discoveries (patterns, insights, tradeoffs)
│  └─ room: advice (workarounds, solutions, runbooks)
│
└─ knowledge_graph (temporal entity facts)
   ├─ Services (deployment status, ownership)
   ├─ Decisions (when made, by whom, rationale)
   └─ Incidents (what failed, why, how fixed)

Accessed by:
├─ Claude Code (MCP plugin or CLI)
├─ chat.lv3.org (MCP server connection)
└─ Scripts (Python SDK)
```

---

## Consequences

### Positive

- **Unified Memory** — Both Claude Code and chat.lv3.org access the same 737+ memories
- **No Duplication** — Decisions made in one interface available to the other
- **Better Context** — Users in chat.lv3.org see what Claude Code agents learned
- **Knowledge Continuity** — Every session (in either interface) adds to the shared pool
- **Cross-Interface Patterns** — Patterns discovered in chat.lv3.org help Claude Code agents

### Negative

- **Shared State Complexity** — Must handle concurrent reads/writes from both interfaces
- **Memory Pollution Risk** — Irrelevant or incorrect memories in chat.lv3.org affect Claude Code
- **Storage Growth** — chat.lv3.org sessions (potentially lengthy) add to palace size
- **Drift Risk** — chat.lv3.org and Claude Code may diverge in how they use memory

### Mitigation

- **Namespace Separation** — chat.lv3.org memories in separate rooms (`room: chat_insights`)
- **Quality Control** — Review/validate important memories before indexing
- **Temporal Windows** — Memories auto-expire after N days if not refreshed
- **Concurrent Access** — SQLite journal mode handles lock contention
- **Monitoring** — Alert if palace grows >1GB or memory quality drops

---

## Evolution Path

| Phase | When | What |
|-------|------|------|
| **Phase 1** | Now | MCP server running on platform; chat.lv3.org connects |
| **Phase 2** | Week 2 | Enable mempalace tools in chat.lv3.org system prompt |
| **Phase 3** | Week 3 | Session auto-save hook for chat.lv3.org (like Claude Code) |
| **Phase 4** | Week 4+ | Chat-specific agent (chat curator) maintains focused diary |
| **Future** | Q2 | Real-time sync: both interfaces push updates to NATS event bus |

---

## Implementation Checklist (Phase 1)

- [ ] Install MemPalace on runtime-control-lv3 (or chat.lv3.org host)
- [ ] Create systemd service for `mempalace-mcp-server`
- [ ] Configure MemPalace MCP server to listen on network socket
- [ ] Add MCP server config to chat.lv3.org configuration
- [ ] Test: Save memory in chat.lv3.org, read in Claude Code
- [ ] Test: Search in chat.lv3.org, verify results are from shared palace
- [ ] Document: Add MemPalace instructions to chat.lv3.org system prompt
- [ ] Monitor: Set up alert if palace becomes unreachable from chat.lv3.org

---

## Deployment Considerations

### Where to Run MemPalace MCP Server

| Location | Pros | Cons |
|----------|------|------|
| **runtime-control-lv3** | Low latency, centralized, shared with Claude Code | Adds load to control plane |
| **Docker container (separate)** | Isolated, scalable, easy to restart | Network latency, needs image |
| **Systemd service (local to chat.lv3.org)** | Simple, low latency | Duplicate palace, memory sync needed |

**Recommendation:** Run on runtime-control-lv3 as systemd service, accessible via internal network (10.10.10.92:5001)

### Storage Considerations

- **Current palace size:** ~188 KB (SQLite database)
- **Expected with chat:** +500KB-1MB per month (conversational data)
- **Compression:** AAAK dialect can reduce by ~30% if needed (experimental)
- **Retention:** Keep memories >30 days by default; archive older memories

---

## Next Steps

1. **Immediate:** Review this ADR, approve architecture choice
2. **Session Today:** Set up MCP server on platform
3. **Phase 1 Complete:** chat.lv3.org can search and save to MemPalace
4. **Phase 2:** Integrate into chat.lv3.org system prompt
5. **Post-Phase 1:** Document lessons and iterate

---

## Links

- ADR 0384: MemPalace Agent Memory System Integration
- MemPalace MCP Server: `python3 -m mempalace.mcp_server --help`
- MemPalace Python API: `from mempalace.searcher import search_memories`
- chat.lv3.org Configuration: See admin docs

## Questions for Review

1. **Option choice:** MCP Server (A) vs HTTP Wrapper (B) vs Webhook (C)?
   - **Recommendation:** A (MCP Server) — simplest and most powerful

2. **Storage location:** runtime-control-lv3 vs separate container vs local?
   - **Recommendation:** runtime-control-lv3 systemd service

3. **Memory namespacing:** Separate rooms for chat.lv3.org memories or shared?
   - **Recommendation:** Shared wing, separate rooms (`room: chat_insights`)

4. **Access control:** Should chat.lv3.org be able to delete/modify memories?
   - **Recommendation:** Read-only for now, write-only to append-only drawers
