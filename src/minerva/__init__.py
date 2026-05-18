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
"""
Minerva — 本地优先深度研究系统。

跨项目桥接:
- minerva → sophia: 测试依赖 sophia.compiler + sophia.learner (paradigm编译)
- minerva → ontoderive: 研究结果可导出为 ontoderive 推导入参
- minerva ← eCOS: eCOS/scripts 中 research_push.py 调用 minerva
- minerva → agora: 共享 MCP 生态 (fastmcp)
"""
