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

import json
import uuid

from fastmcp import FastMCP

from minerva.executor.executor import ExecutionMode, ResearchExecutor, ResearchTask

# --- Create MCP server ---

mcp = FastMCP(
    "Minerva Deep Research",
    mask_error_details=True,
)

# Global executor (initialized at startup via init_server()).
# Design note: singleton pattern is intentional — loading LLM/search/pipeline/KB
# at MCP connect time would add 5-10s latency to every tool call.
executor: ResearchExecutor | None = None


class DegradedExecutor:
    """Lightweight executor with only knowledge store access.

    Used when full executor (LLM+pipeline) fails to initialize. Provides
    knowledge_search and knowledge_ingest; research tools return clear errors.
    """
    def __init__(self, kb):
        self.kb = kb

    async def get_status(self, task_id: str):
        return None

    async def execute_now(self, task):
        raise RuntimeError("Research not available in degraded mode. Only knowledge_search and knowledge_ingest work.")

    async def schedule(self, task):
        raise RuntimeError("Schedule not available in degraded mode.")

    async def watch(self, task):
        raise RuntimeError("Watch not available in degraded mode.")


def _ensure_executor():
    """Return executor or raise with clear guidance."""
    if executor is not None:
        return executor
    raise RuntimeError(
        "Minerva MCP server not initialized. "
        "Start with: minerva-mcp or configure your MCP client to launch minerva."
    )


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
        result = await _ensure_executor().execute_now(task)
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
        task_id = await _ensure_executor().schedule(task)
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
        task_id = await _ensure_executor().watch(task)
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
    results = await _ensure_executor().kb.search(query, mode)
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
    result = await _ensure_executor().kb.ingest(source, source_type)
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
    """Entry point: minerva-mcp — auto-initializes executor with graceful degradation."""
    print("Minerva MCP Server starting...")

    # Try full executor init first (LLM + pipeline + KB + cost_guard)
    try:
        from minerva.config import MinervaConfig
        from minerva.executor.executor import CostGuard, ResearchExecutor
        from minerva.knowledge.store import SQLiteKnowledgeStore
        from minerva.llm.client import OpenAICompatibleClient
        from minerva.pipeline.engine import create_default_pipeline
        from minerva.search.engine import SearchEngine
        from minerva.triage.router import TriageRouter

        config = MinervaConfig.load()
        llm = OpenAICompatibleClient(base_url=config.llm.base_url, model=config.llm.models["agent"])
        search = SearchEngine({
            "searxng_url": config.search.searxng_url,
            "metaso_api_key": config.search.metaso_api_key,
            "exa_api_key": config.search.exa_api_key,
        })
        pipeline = create_default_pipeline(llm, search, None, None)
        triage = TriageRouter(llm)
        kb = SQLiteKnowledgeStore()
        cost_guard = CostGuard(monthly_budget=config.execution.monthly_budget_usd)
        init_server(ResearchExecutor(
            triage_router=triage, pipeline=pipeline, knowledge_store=kb, cost_guard=cost_guard,
        ))
        print("  Full executor initialized: research + search + ingest all available.")
    except Exception as e:
        print(f"  [WARNING] Full executor init failed: {e}")
        print("  Trying degraded mode: knowledge_search + knowledge_ingest only...")
        # Degraded mode: create a minimal executor with just the knowledge store
        try:
            from minerva.knowledge.store import SQLiteKnowledgeStore
            kb = SQLiteKnowledgeStore()
            init_server(DegradedExecutor(kb))
            print("  Degraded mode ready: knowledge_search + knowledge_ingest available.")
        except Exception as e2:
            print(f"  [ERROR] Degraded init also failed: {e2}")
            print("  No tools available.")

    print("Configure your MCP client to connect to this server.")
    mcp.run()


if __name__ == "__main__":
    main()
