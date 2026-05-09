"""Minerva CLI — entry point for deep research commands."""

from __future__ import annotations

import argparse
import asyncio


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="minerva",
        description="Minerva — Local-First Deep Research System",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # research
    r = sub.add_parser("research", help="Execute deep research")
    r.add_argument("query", help="Research question")
    r.add_argument("--level", default="auto", choices=["auto", "L0", "L1", "L2", "L3", "L4"],
                   help="Pipeline level (default: auto)")
    r.add_argument("--max-cost", type=float, default=1.0, help="Max cost in USD")

    # mcp
    sub.add_parser("mcp", help="Start MCP server for agent integration")

    # check
    sub.add_parser("check", help="Health check — verify all services are running")

    # daemon (Phase 2 stub)
    sub.add_parser("daemon", help="Start background daemon (Phase 2)")

    return parser


async def _run_research(args):
    """Execute a research query."""
    from minerva.config import MinervaConfig
    from minerva.llm.client import OpenAICompatibleClient
    from minerva.triage.router import TriageRouter, ResearchLevel
    from minerva.pipeline.engine import create_default_pipeline
    from minerva.search.engine import SearchEngine

    config = MinervaConfig.load()
    llm = OpenAICompatibleClient(
        base_url=config.llm.base_url,
        model=config.llm.models["agent"],
    )
    search = SearchEngine({"searxng_url": config.search.searxng_url})

    level = ResearchLevel(args.level) if args.level != "auto" else None
    if level is None:
        router = TriageRouter(llm)
        triage = await router.classify(args.query)
        level = triage.level
        print(f"Auto-routed to {level.value} (cost est: ${triage.cost_estimate:.2f})")
        triage_obj = triage
    else:
        router = TriageRouter(llm)
        triage_obj = await router.classify(args.query)

    pipeline = create_default_pipeline(llm, search, None, None)
    ctx = await pipeline.run(args.query, level, triage_obj)

    if ctx.report:
        print(ctx.report)
        print(f"\n---\nReport saved to: {ctx.report_path}")
    else:
        print("Research completed but no report generated.")

    return 0


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "research":
        return asyncio.run(_run_research(args))
    elif args.command == "mcp":
        print("Starting Minerva MCP Server...")
        print("Configure your MCP client (Claude Code/Codex/Cursor) to connect.")
        return 0
    elif args.command == "check":
        print("Minerva health check:")
        print("  [TODO] SearXNG: check localhost:8080")
        print("  [TODO] Ollama: check localhost:11434")
        print("  [TODO] Neo4j: Phase 2")
        return 0
    elif args.command == "daemon":
        from minerva.executor.daemon import main as daemon_main
        return daemon_main()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
