# Minerva Architecture

## Overview

Minerva is a tiered deep research system with three levels of dependency and four layers of architecture.

### Design Principles

1. **Runs on a laptop first** — M5 128GB is the reference hardware
2. **Degrades gracefully** — every Tier 2 component has a Tier 1 fallback
3. **MCP is the only integration surface** — no agent-specific bindings
4. **Knowledge is the product, not the byproduct** — every research run enriches the knowledge base
5. **Cost-aware** — every operation has a cost estimate, monthly budget enforced

### Three-Tier Dependency Model

```
🟢 Tier 1 (Hard): Must be available. System fails without these.
   - Ollama MLX (local LLM)
   - SQLite FTS5 (full-text search)
   - LanceDB (vector search)
   - SearXNG (web search, self-hosted)
   - llm-wiki-agent (document → wiki)

🟡 Tier 2 (Enhanced): Graceful degradation when missing.
   - Graphiti + Neo4j (temporal knowledge graph)
   - Semantica (SHACL ontology + Allen temporal + Datalog reasoning)
   - Exa API (semantic web search)
   - NotebookLM (creative output)

🔵 Tier 3 (Inspiration): Design patterns only, no code dependency.
   - SharedBrain B-OS architecture patterns
   - KGGPT three-layer entity extraction
```

### Four-Layer Architecture

```
Layer 1: Agent Integration (MCP Server)
   5 Super Tools: research_now | research_schedule | research_watch |
                  knowledge_search | knowledge_ingest

Layer 2: Execution Engine
   Immediate Queue | Cron Scheduler | Watch Event Loop
   Triage Router (L0-L4 classification)
   Cost Guard (budget enforcement)

Layer 3: Research Pipeline
   L0 Quick → L1 Standard → L2 Deep → L3 Comprehensive → L4 Max
   Each level: Search → Extract → Analyze → Reason → Output

Layer 4: Knowledge Base
   Storage: Markdown + SQLite FTS5 + LanceDB + (Neo4j)
   Ontology: Semantica (SHACL + SKOS)
   Maintenance: freshness checks, contradiction detection, cascade updates
```

## System Context

```
┌──────────┐  ┌──────────┐  ┌──────────┐
│Claude Code│  │  Codex   │  │ Cursor   │  ... any MCP client
└─────┬─────┘  └────┬─────┘  └────┬─────┘
      │              │              │
      └──────────────┴──────────────┘
                     │
              MCP Protocol
                     │
            ┌────────┴────────┐
            │  Minerva MCP    │
            │  Server         │
            └────────┬────────┘
                     │
            ┌────────┴────────┐
            │  Minerva Core   │
            │  (Pipeline +    │
            │   Knowledge)    │
            └────────┬────────┘
                     │
     ┌───────────────┼───────────────┐
     │               │               │
┌────┴────┐   ┌──────┴──────┐  ┌────┴────┐
│ Ollama  │   │  SearXNG    │  │ Neo4j   │
│ (local) │   │  (search)   │  │ (graph) │
└─────────┘   └─────────────┘  └─────────┘
     │               │               │
     └───────────────┴───────────────┘
                     │
         DeepSeek V4 / GLM-5 / Exa
         (cloud APIs, cost-gated)
```
