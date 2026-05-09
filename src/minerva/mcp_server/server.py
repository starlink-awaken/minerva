"""
Minerva MCP Server — Expose deep research as Model Context Protocol tools.

Implements 5 Super Tools (Dropbox Dash pattern):
- research_now: Execute research immediately
- research_schedule: Schedule recurring research
- research_watch: Watch topics for new content
- knowledge_search: Search existing knowledge base
- knowledge_ingest: Ingest new content into knowledge base

Any MCP-compatible agent (Claude Code, Codex, Cursor) can call these.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastmcp import FastMCP

from minerva.executor.executor import ExecutionMode, ResearchExecutor, ResearchTask

# --- Create MCP server ---

mcp = FastMCP(
    "Minerva Deep Research",
    description="Local-first deep research system with tiered pipelines and knowledge management",
)

# Global executor (initialized at startup)
executor: ResearchExecutor | None = None


# ============================================================
# Tool: research_now
# ============================================================

@mcp.tool()
async def research_now(
    query: str,
    level: str = "auto",
    max_cost: float = 1.0,
) -> str:
    """Execute deep research immediately. Auto-routes to appropriate pipeline level.

    Use when: You or the user need an answer NOW.
    Levels: L0=30s/$0, L1=3min/$0, L2=10min/~$0.30, L3=20min/~$2, L4=30min+/$5-10.
    Default 'auto' classifies the query and picks the right level.

    Args:
        query: The research question to investigate
        level: Pipeline level — auto|L0|L1|L2|L3|L4 (default: auto)
        max_cost: Maximum cost in USD for this research (default: 1.0)
    """
    task = ResearchTask(
        id=str(uuid.uuid4())[:8],
        query=query,
        mode=ExecutionMode.IMMEDIATE,
        level=level,
        max_cost=max_cost,
    )

    try:
        result = await executor.execute_now(task)
    except Exception as exc:
        return json.dumps({"status": "failed", "error": str(exc)})

    return json.dumps({
        "status": "completed",
        "task_id": result.task_id,
        "summary": result.summary,
        "report_path": result.report_path,
        "cost": result.cost,
        "completed_at": result.completed_at,
    }, ensure_ascii=False, indent=2)


# ============================================================
# Tool: research_schedule
# ============================================================

@mcp.tool()
async def research_schedule(
    query: str,
    cron: str,
    level: str = "auto",
    notify: str = "mcp",
) -> str:
    """Schedule recurring research. Runs on a cron schedule.

    Use when: You want daily/weekly briefings on a topic.
    Examples: "0 8 * * *" = every day at 8am, "0 9 * * 1" = every Monday at 9am

    Args:
        query: Research question to investigate on schedule
        cron: Cron expression for execution timing
        level: Pipeline level (default: auto)
        notify: Notification method — mcp|none (default: mcp)
    """
    task = ResearchTask(
        id=str(uuid.uuid4())[:8],
        query=query,
        mode=ExecutionMode.SCHEDULED,
        level=level,
        max_cost=1.0,
        cron_expr=cron,
        notify=notify,
    )

    try:
        task_id = await executor.schedule(task)
    except Exception as exc:
        return json.dumps({"status": "failed", "error": str(exc)})

    return json.dumps({
        "status": "scheduled",
        "task_id": task_id,
        "cron": cron,
        "next_run": "calculated_at_runtime",
    }, ensure_ascii=False, indent=2)


# ============================================================
# Tool: research_watch
# ============================================================

@mcp.tool()
async def research_watch(
    topic: str,
    sources: str = "arxiv",
    check_interval: str = "daily",
    max_cost_per_run: float = 1.0,
) -> str:
    """Watch a topic for new content. Automatically researches when new content appears.

    Use when: You want to track a research area and be notified of developments.

    Args:
        topic: Topic to watch (e.g., "transformer architecture", "CRISPR")
        sources: Comma-separated sources — arxiv,github_trending,techcrunch,reddit,zhihu
        check_interval: How often to check — hourly|daily|weekly (default: daily)
        max_cost_per_run: Max cost per triggered research (default: 1.0)
    """
    task = ResearchTask(
        id=str(uuid.uuid4())[:8],
        query=f"[WATCH] {topic}",
        mode=ExecutionMode.WATCH,
        level="L2",
        max_cost=max_cost_per_run,
        topic=topic,
        sources=[s.strip() for s in sources.split(",")],
        check_interval=check_interval,
    )

    try:
        task_id = await executor.watch(task)
    except Exception as exc:
        return json.dumps({"status": "failed", "error": str(exc)})

    return json.dumps({
        "status": "watching",
        "task_id": task_id,
        "topic": topic,
        "sources": task.sources,
        "check_interval": check_interval,
    }, ensure_ascii=False, indent=2)


# ============================================================
# Tool: knowledge_search
# ============================================================

@mcp.tool()
async def knowledge_search(
    query: str,
    mode: str = "hybrid",
) -> str:
    """Search the existing knowledge base.

    Modes:
    - hybrid: All search methods combined (RRF fused) — best for most queries
    - fulltext: Keyword search via SQLite FTS5
    - semantic: Vector similarity search via LanceDB
    - graph: Entity relationship traversal
    - timeline: Time-ordered entity/event search

    Args:
        query: What to search for
        mode: Search mode (default: hybrid)
    """
    # Delegate to knowledge store
    results = await executor.kb.search(query, mode)
    return json.dumps({
        "query": query,
        "mode": mode,
        "results": results[:20],  # Top 20
        "total": len(results),
    }, ensure_ascii=False, indent=2)


# ============================================================
# Tool: knowledge_ingest
# ============================================================

@mcp.tool()
async def knowledge_ingest(
    source: str,
    source_type: str = "auto",
) -> str:
    """Ingest new content into the knowledge base.

    Supported types: url, pdf, markdown, code, or auto (detect from source).

    Args:
        source: URL or local file path to ingest
        source_type: Content type (default: auto)
    """
    # Delegate to knowledge store
    result = await executor.kb.ingest(source, source_type)
    return json.dumps({
        "status": "ingested",
        "source": source,
        "type": source_type,
        "entities_extracted": result.get("entity_count", 0),
        "relations_found": result.get("relation_count", 0),
    }, ensure_ascii=False, indent=2)


# ============================================================
# Server lifecycle
# ============================================================

def init_server(executor_instance: ResearchExecutor):
    """Initialize the MCP server with an executor."""
    global executor
    executor = executor_instance


def main():
    """Entry point: minerva-mcp"""
    import sys
    print("Minerva MCP Server starting...")
    print("Configure your MCP client to connect to this server.")
    print("Example Claude Code config (~/.claude/mcp.json):")
    print(json.dumps({
        "mcpServers": {
            "minerva": {
                "command": "minerva-mcp",
                "env": {"MINERVA_HOME": "~/minerva"}
            }
        }
    }, indent=2))
    mcp.run()


if __name__ == "__main__":
    main()


# ============================================================
# Pseudocode for MCP tool execution flow
# ============================================================

"""
FLOW: Agent calls research_now via MCP
======================================

1. MCP Client (Claude Code/Codex) sends:
   {
     "method": "tools/call",
     "params": {
       "name": "research_now",
       "arguments": {
         "query": "What is the latest in MoE architecture?",
         "level": "auto",
         "max_cost": 1.0
       }
     }
   }

2. Minerva MCP Server receives → validates parameters → calls research_now()

3. research_now():
   a. Create ResearchTask with unique ID
   b. executor.execute_now(task):
      - TriageRouter.classify(query) → L2 Deep
      - CostGuard.check(0.30) → OK
      - Pipeline.run(query, L2):
        * DecomposeStage: 10 sub-questions
        * MultiSourceSearchStage: SearXNG + Exa + Scholar → 25 results
        * EntityExtractionStage: spaCy NER → 45 entities
        * DeepReadStage: V4-Flash cross-analysis
        * CrossAnalyzeStage: R1-70B reasoning
        * QualityGateStage: all checks pass
        * OutputStage: report generated → ~/knowledge/reports/
      - CostGuard.record(0.28)
   c. Return ResearchResult

4. MCP Server serializes result to JSON and returns to Agent

5. Agent presents to user:
   "Research complete. Report at ~/knowledge/reports/2026-05-09_moe-architecture.md
    Summary: MoE architecture has evolved from simple top-k routing to..."
"""
