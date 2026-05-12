"""Minerva CLI — entry point for deep research commands."""

from __future__ import annotations

import argparse
import asyncio
import os


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

    # maintenance (Phase 3)
    mt = sub.add_parser("maintenance", help="Knowledge base maintenance — staleness, gaps, contradictions")
    mt.add_argument("--action", default="all", choices=["all", "staleness", "gaps", "contradictions"],
                    help="Maintenance action to run (default: all)")

    return parser


async def _run_research(args):
    """Execute a research query."""
    from minerva.config import MinervaConfig
    from minerva.llm.client import OpenAICompatibleClient
    from minerva.pipeline.engine import create_default_pipeline
    from minerva.search.engine import SearchEngine
    from minerva.triage.router import ResearchLevel, TriageRouter
    from minerva.utils.terminal import print_banner, print_pipeline_header, print_summary_table

    config = MinervaConfig.load()
    print_banner()
    llm = OpenAICompatibleClient(
        base_url=config.llm.base_url,
        model=config.llm.models["agent"],
    )
    # Enterprise reasoning: DeepSeek V4 Pro for L3/L4 stages
    cloud_llm = None
    if os.environ.get("DEEPSEEK_API_KEY"):
        cloud_llm = OpenAICompatibleClient(
            base_url="https://api.deepseek.com/v1",
            api_key=os.environ["DEEPSEEK_API_KEY"],
            model="deepseek-chat",
            timeout=180,
        )
    # Free 128K context model for DeepRead + Chinese tasks
    glm_llm = None
    if os.environ.get("GLM_API_KEY"):
        glm_llm = OpenAICompatibleClient(
            base_url="https://open.bigmodel.cn/api/paas/v4",
            api_key=os.environ["GLM_API_KEY"],
            model="glm-4.7-flash",
            timeout=120,
        )
    search = SearchEngine({
        "searxng_url": config.search.searxng_url,
        "metaso_api_key": config.search.metaso_api_key,
        "exa_api_key": config.search.exa_api_key,
        "zhipu_api_key": os.environ.get("ZHIPU_API_KEY", ""),
    })

    # Load spaCy NLP pipelines for entity extraction
    nlp = None
    nlp_zh = None
    try:
        import spacy
        nlp = spacy.load(config.nlp.spacy_model)
    except Exception:
        pass
    try:
        import spacy
        nlp_zh = spacy.load(config.nlp.spacy_model_zh)
    except Exception:
        pass

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

    print_pipeline_header(args.query, level.value)

    pipeline = create_default_pipeline(llm, search, nlp, None, nlp_pipeline_zh=nlp_zh, cloud_llm_client=cloud_llm, glm_llm_client=glm_llm)
    ctx = await pipeline.run(args.query, level, triage_obj)

    if ctx.report:
        quality_score = "N/A"
        zh_path = None
        for r in (ctx.relations or []):
            if "quality_score" in r:
                quality_score = str(r["quality_score"])
            if "zh_report_path" in r:
                zh_path = r["zh_report_path"]
        print_summary_table(
            ctx.stage_timings, quality_score,
            len(ctx.search_results), len(ctx.entities),
            sum(ctx.stage_timings.values()),
        )
        print(ctx.report)
        print(f"\n[bold]Reports saved:[/bold]")
        print(f"  EN: {ctx.report_path}")
        if zh_path:
            print(f"  ZH: {zh_path}")
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
        from minerva.mcp_server.server import main as mcp_main
        return mcp_main()
    elif args.command == "check":
        print("Minerva health check:")
        print("  [TODO] SearXNG: check localhost:8080")
        print("  [TODO] Ollama: check localhost:11434")
        print("  [TODO] Neo4j: Phase 2")
        return 0
    elif args.command == "daemon":
        from minerva.executor.daemon import main as daemon_main
        return daemon_main()
    elif args.command == "maintenance":
        return _run_maintenance(args)

    return 0


def _run_maintenance(args) -> int:
    """Run knowledge base maintenance."""

    from minerva.maintenance.contradiction import detect_contradictions_rule_based
    from minerva.maintenance.gap_analyzer import get_improvement_suggestions
    from minerva.maintenance.staleness import StalenessChecker

    action = args.action
    report_dir = "~/knowledge/reports"

    if action in ("all", "staleness"):
        print("=== Staleness Check ===")
        checker = StalenessChecker(report_dir=report_dir)
        report = checker.scan()
        print(report.summary)
        if report.stale_entries:
            for e in report.stale_entries[:5]:
                print(f"  [{e.age_days}d] {e.title[:60]} — {e.reason[:80]}")

    if action in ("all", "gaps"):
        print("\n=== Gap Analysis ===")
        suggestions = get_improvement_suggestions(report_dir=report_dir)
        for s in suggestions:
            print(f"  - {s}")

    if action in ("all", "contradictions"):
        print("\n=== Contradiction Detection ===")
        from minerva.maintenance.contradiction import extract_claims
        all_entries = extract_claims(report_dir, limit=20)
        if all_entries:
            contradictions = detect_contradictions_rule_based(all_entries)
            print(f"Scanned {len(all_entries)} claims from reports.")
            if contradictions:
                print(f"Found {len(contradictions)} potential contradictions:")
                for c in contradictions[:5]:
                    print(f"  [{c.severity}] {c.claim_a[:50]} vs {c.claim_b[:50]}")
            else:
                print("No contradictions detected.")
        else:
            print("No claims found to analyze.")

    print("\nMaintenance complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
