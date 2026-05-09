"""
Minerva — Local-First Deep Research System.

Usage:
    from minerva.triage.router import TriageRouter
    from minerva.pipeline.engine import create_default_pipeline
    from minerva.executor.executor import ResearchExecutor, CostGuard
    from minerva.knowledge.store import create_knowledge_store
    from minerva.search.engine import SearchEngine
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = [
    "TriageRouter",
    "create_default_pipeline",
    "ResearchExecutor",
    "CostGuard",
    "create_knowledge_store",
    "SearchEngine",
]
