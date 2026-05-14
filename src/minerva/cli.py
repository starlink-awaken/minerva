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

    # init
    sub.add_parser("init", help="First-time setup wizard")

    # research
    r = sub.add_parser("research", help="Execute deep research")
    r.add_argument("query", nargs="?", help="Research question (or use --template)")
    r.add_argument("--level", default="auto", choices=["auto", "L0", "L1", "L2", "L3", "L4"],
                   help="Pipeline level (default: auto)")
    r.add_argument("--max-cost", type=float, default=1.0, help="Max cost in USD")
    r.add_argument("--template", choices=["competitor-analysis", "literature-review", "policy-audit"],
                   help="Use a research template")
    r.add_argument("--target", help="Template target (replaces {{target}}, {{topic}}, {{policy}} in template)")

    # mcp
    sub.add_parser("mcp", help="Start MCP server for agent integration")

    # check
    sub.add_parser("check", help="Health check — verify all services are running")

    # daemon
    sub.add_parser("daemon", help="Start background daemon")

    # web
    sub.add_parser("web", help="Start FastAPI web server (http://localhost:8765)")

    # maintenance
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
    # Enterprise reasoning — V4 Pro (1M ctx, 2.5折) primary, LongCat free backup
    cloud_llm = None
    if os.environ.get("DEEPSEEK_API_KEY"):
        cloud_llm = OpenAICompatibleClient(
            base_url="https://api.deepseek.com",
            api_key=os.environ["DEEPSEEK_API_KEY"],
            model="deepseek-v4-pro",
            timeout=180,
        )
    elif os.environ.get("LONGCAT_API_KEY"):
        cloud_llm = OpenAICompatibleClient(
            base_url="https://api.longcat.chat/openai",
            api_key=os.environ["LONGCAT_API_KEY"],
            model="LongCat-Flash-Thinking",
            timeout=180,
        )
    # 1M context for DeepRead — V4 Pro priority, GLM free fallback
    long_context = cloud_llm  # V4 Pro has 1M ctx
    if not long_context and os.environ.get("GLM_API_KEY"):
        long_context = OpenAICompatibleClient(
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

    # Template support: load template and interpolate {{variables}}
    if args.template and args.target:
        from pathlib import Path as _Path
        tpl_path = _Path(__file__).parent.parent.parent / "templates" / f"{args.template}.md"
        if tpl_path.exists():
            template_content = tpl_path.read_text()
            template_content = template_content.replace("{{target}}", args.target)
            template_content = template_content.replace("{{topic}}", args.target)
            template_content = template_content.replace("{{policy}}", args.target)
            print(f"Using template: {args.template} (target: {args.target})")
            if not args.query:
                args_query = template_content.split("\n")[0].lstrip("# ").strip()
                args = argparse.Namespace(**{**vars(args), "query": args_query})
            print(f"Template sub-questions loaded: {template_content.count('What ')} questions")

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

    # Research Paradigm — classify problem type → apply framework
    from minerva.paradigm.router import classify_paradigm
    from minerva.paradigm.types import PARADIGMS
    paradigm_result = await classify_paradigm(llm, args.query)
    paradigm_def = PARADIGMS[paradigm_result.paradigm]
    print(f"\n  [bold cyan]Paradigm:[/bold cyan] {paradigm_def.name} ({paradigm_result.confidence:.0%} confidence)")
    print(f"  [dim]Reasoning: {paradigm_result.reasoning}[/dim]")
    print(f"  [dim]Stages: {' → '.join(paradigm_def.stages)}[/dim]")
    print(f"  [dim]Verification: {paradigm_def.verification_mode.value.upper()}[/dim]")

    pipeline = create_default_pipeline(llm, search, nlp, None, nlp_pipeline_zh=nlp_zh, cloud_llm_client=cloud_llm, glm_llm_client=long_context)
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
        print("\n[bold]Reports saved:[/bold]")
        print(f"  EN: {ctx.report_path}")
        if zh_path:
            print(f"  ZH: {zh_path}")
    else:
        print("Research completed but no report generated.")

    return 0


def _run_init() -> int:
    """First-time setup wizard."""
    from pathlib import Path as _Path
    import os

    print("\n  ⚡ Minerva — First-Time Setup\n")
    checks = []

    # 1. Ollama
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=5)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            print(f"  ✅ Ollama running ({len(models)} models)")
            checks.append(("Ollama", True))
        else:
            raise Exception("not ok")
    except Exception:
        print("  ⚠️  Ollama not detected. Install: brew install ollama && ollama serve")
        checks.append(("Ollama", False))

    # 2. Config
    config_path = _Path(__file__).parent.parent.parent / "config" / "minerva.yaml"
    if config_path.exists():
        print(f"  ✅ Config found: {config_path}")
        checks.append(("Config", True))
    else:
        print(f"  ⚠️  Config not found at {config_path}")
        checks.append(("Config", False))

    # 3. Knowledge dirs
    for d in ["~/knowledge/reports", "~/minerva/state"]:
        _Path(d).expanduser().mkdir(parents=True, exist_ok=True)
    print("  ✅ Knowledge directories created")
    checks.append(("Storage", True))

    # 4. API keys
    keys = {"DEEPSEEK_API_KEY": "DeepSeek", "GLM_API_KEY": "GLM", "EXA_API_KEY": "Exa", "METASO_API_KEY": "Metaso"}
    for env, name in keys.items():
        if os.environ.get(env):
            print(f"  ✅ {name} API key configured")
        else:
            print(f"  ⚠️  {name} API key not set (optional)")

    # 5. spaCy
    try:
        import spacy
        spacy.load("en_core_web_lg")
        print("  ✅ spaCy en_core_web_lg available")
    except Exception:
        print("  ⚠️  spaCy model not found. Run: python -m spacy download en_core_web_lg")

    print(f"\n  Setup complete. {sum(1 for _,ok in checks if ok)}/{len(checks)} checks passed.")
    print("  Run: minerva web    → start the dashboard")
    print("  Run: minerva research \"your question\" → test the pipeline\n")
    return 0


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "init":
        return _run_init()
    elif args.command == "research":
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
    elif args.command == "web":
        import uvicorn
        from minerva.web.app import app
        print("Minerva Web → http://localhost:8765")
        uvicorn.run(app, host="0.0.0.0", port=8765, log_level="info")
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
