# Minerva — Local-First Deep Research System

> Minerva: Roman goddess of wisdom, strategic warfare, and the arts. Often depicted with an owl.

A local-first, multi-tier deep research system that combines LLM-powered analysis with structured knowledge management, temporal reasoning, and agent integration via MCP. Designed to run primarily on local hardware (Apple Silicon M-series, 64GB+ RAM) with optional cloud API augmentation.

## Philosophy

- **Local-first by default** — your data never leaves your machine unless you choose to
- **Knowledge compounds** — every research session builds on previous ones
- **Tiered execution** — from 30-second quick lookups to 30-minute comprehensive analyses
- **Source-grounded** — every claim traceable to its origin
- **Open standards** — MCP for agent integration, Markdown for knowledge storage, SHACL for ontology validation

## Quick Start

```bash
# Install
pip install minerva

# Start the MCP server (for Claude Code / Codex / Cursor integration)
minerva-mcp

# Or run research directly
minerva research "What's the latest in MoE architecture?"
```

## Architecture

```
User/Agent
    │
    ▼
MCP Server (5 Super Tools)
    │
    ▼
Triage Router (L0-L4 classification)
    │
    ▼
Pipeline Executor
    │
    ├── Search Layer (SearXNG + Exa + Semantic Scholar + 秘塔)
    ├── Extraction Layer (spaCy NLP + LLM fallback)
    ├── Knowledge Layer (Markdown wiki + LanceDB + Neo4j/Kuzu)
    ├── Reasoning Layer (Semantica temporal + Datalog)
    └── Output Layer (reports + NotebookLM creative)
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — system architecture and design decisions
- [Design](docs/DESIGN.md) — detailed technical design
- [API Reference](docs/API.md) — MCP tools and Python API
- [Guides](docs/guides/) — setup, configuration, and usage guides

## License

MIT
