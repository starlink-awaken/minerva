"""Minerva daemon — background process for scheduled/watch execution modes."""

from __future__ import annotations

import asyncio
import contextlib
import signal
import time


def main():
    """Start Minerva daemon with scheduled + watch execution loops."""
    print("Minerva daemon starting...")
    return asyncio.run(_run_daemon())


async def _run_daemon() -> int:
    """Main daemon event loop with graceful shutdown."""
    # Load dependencies
    from minerva.config import MinervaConfig
    from minerva.executor.executor import CostGuard, ResearchExecutor
    from minerva.knowledge.store import SQLiteKnowledgeStore
    from minerva.llm.client import OpenAICompatibleClient
    from minerva.pipeline.engine import create_default_pipeline
    from minerva.search.engine import SearchEngine
    from minerva.triage.router import TriageRouter

    config = MinervaConfig.load()
    llm = OpenAICompatibleClient(
        base_url=config.llm.base_url,
        model=config.llm.models["agent"],
    )
    search = SearchEngine({
        "searxng_url": config.search.searxng_url,
        "metaso_api_key": config.search.metaso_api_key,
    })

    # Load spaCy if available
    nlp = None
    try:
        import spacy
        nlp = spacy.load(config.nlp.spacy_model)
    except Exception:
        pass

    pipeline = create_default_pipeline(llm, search, nlp, None)
    triage = TriageRouter(llm)
    kb = SQLiteKnowledgeStore()
    cost_guard = CostGuard(monthly_budget=config.execution.monthly_budget_usd)

    executor = ResearchExecutor(
        triage_router=triage,
        pipeline=pipeline,
        knowledge_store=kb,
        cost_guard=cost_guard,
        state_dir=config.state_dir,
    )

    # Restore persisted state
    restored = executor.restore_state()
    print(f"Restored {restored['scheduled']} scheduled, {restored['watch']} watch tasks.")

    # Handle shutdown
    shutdown_event = asyncio.Event()

    def _signal_handler():
        print("\nShutting down daemon...")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _signal_handler)

    # Status heartbeat
    async def _heartbeat():
        while not shutdown_event.is_set():
            status = executor.health_check()
            print(f"[daemon] {time.strftime('%H:%M:%S')} "
                  f"scheduled={status['scheduled']} watch={status['watch']} "
                  f"budget_used=${status['budget_used']:.2f}")
            await asyncio.sleep(60)

    heartbeat_task = asyncio.create_task(_heartbeat())

    print("Daemon ready. Scheduled + watch modes active.")
    await shutdown_event.wait()

    # Graceful cleanup
    heartbeat_task.cancel()
    executor.persist_state()
    print("Daemon stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
