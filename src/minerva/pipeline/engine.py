"""
Minerva Pipeline Engine — Tiered research pipeline execution.

Executes research at L0-L4 levels with pluggable, composable stages.
Each level is a predefined sequence of stages with appropriate models and budgets.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import structlog

from minerva.triage.router import ResearchLevel, TriageResult

logger = structlog.get_logger(__name__)


# ============================================================
# Data Models
# ============================================================

@dataclass
class ResearchContext:
    """Mutable context passed through pipeline stages."""
    query: str
    level: ResearchLevel
    triage: TriageResult

    # Populated by stages
    sub_questions: list[str] = field(default_factory=list)
    search_results: list[dict] = field(default_factory=list)
    extracted_content: list[str] = field(default_factory=list)
    entities: list[dict] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)
    contradictions: list[dict] = field(default_factory=list)
    report: str | None = None
    report_path: str | None = None

    # Metrics
    cost: float = 0.0
    started_at: str | None = None
    completed_at: str | None = None
    stage_timings: dict[str, float] = field(default_factory=dict)


# ============================================================
# Stage Interface
# ============================================================

class IPipelineStage(ABC):
    """A single stage in the research pipeline."""

    name: str = "base_stage"

    @abstractmethod
    async def execute(self, ctx: ResearchContext) -> ResearchContext:
        """Execute this stage. Returns (possibly mutated) context."""
        ...


# ============================================================
# Pipeline Definition
# ============================================================

class Pipeline:
    """Execute tiered research pipelines.

    Usage:
        pipeline = Pipeline(stages_by_level)
        ctx = await pipeline.run("What is MoE?", ResearchLevel.L2)
    """

    def __init__(self, stages: dict[ResearchLevel, list[IPipelineStage]]):
        self.stages = stages

    async def run(self, query: str, level: ResearchLevel, triage: TriageResult) -> ResearchContext:
        """Execute pipeline at given level.

        Flow:
        1. Create ResearchContext with query, level, triage
        2. For each stage in stages[level]:
           a. Execute stage
           b. Log timing
           c. Check for QualityGate failure → retry
        3. Return completed context
        """
        ctx = ResearchContext(query=query, level=level, triage=triage)

        import time
        stage_list = self.stages.get(level, [])
        retries = 0
        max_retries = 2

        i = 0
        while i < len(stage_list):
            stage = stage_list[i]
            t0 = time.time()

            try:
                ctx = await stage.execute(ctx)
            except QualityGateFailure:
                if retries < max_retries:
                    logger.warning("quality_gate_failed", stage=stage.name, retry=retries + 1)
                    retries += 1
                    i = max(0, i - 2)  # Go back 2 stages, retry DeepRead
                    continue
                else:
                    logger.error("quality_gate_max_retries", max_retries=max_retries)
                    # Proceed with degraded quality

            elapsed = time.time() - t0
            ctx.stage_timings[stage.name] = elapsed
            logger.info("stage_complete", stage=stage.name, elapsed_s=elapsed, cost=ctx.cost)
            i += 1

        ctx.completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return ctx


class QualityGateFailure(Exception):
    """Raised when research quality checks fail."""
    pass


# ============================================================
# Pipeline Factory
# ============================================================

def create_default_pipeline(
    llm_client,
    search_engine,
    nlp_pipeline,
    knowledge_store,
    creative_tool=None,
    nlp_pipeline_zh=None,
    cloud_llm_client=None,
    glm_llm_client=None,
) -> Pipeline:
    """Create pipeline with default stage configurations for each level.

    L0-L2 use local llm_client. L3-L4 use cloud_llm_client (DeepSeek V4 Pro).
    DeepRead uses glm_llm_client (GLM-4.7 Flash, 128K context, free) when available.
    """

    from minerva.pipeline.stages import (
        CounterArgumentStageImpl,
        CrossAnalyzeStageImpl,
        DecomposeStageImpl,
        DeepReadStageImpl,
        EntityExtractionStageImpl,
        ExtendedOutputStageImpl,
        MultiModelVotingStageImpl,
        MultiSourceSearchStageImpl,
        OutputStageImpl,
        QualityGateStageImpl,
    )

    # L3/L4 use cloud client for enterprise reasoning (DeepSeek V4 Pro).
    # Falls back to local qwen3.6:27b if cloud is unavailable.
    reasoner = cloud_llm_client or llm_client
    # DeepRead uses cloud client (V4 Pro 1M ctx) > GLM (128K free) > local
    long_context = cloud_llm_client or glm_llm_client or llm_client

    stages = {
        ResearchLevel.L0: [
            MultiSourceSearchStageImpl(search_engine, backends=["ddg", "scholar", "metaso", "exa", "brave", "zhipu"], max_results=5),
            QualityGateStageImpl(),
            OutputStageImpl(llm_client=llm_client, knowledge_store=knowledge_store),
        ],
        ResearchLevel.L1: [
            DecomposeStageImpl(llm_client, max_sub_questions=5),
            MultiSourceSearchStageImpl(search_engine, backends=["ddg", "scholar", "metaso", "exa", "brave", "zhipu"], max_results=10),
            CrossAnalyzeStageImpl(llm_client),
            OutputStageImpl(llm_client=llm_client, knowledge_store=knowledge_store),
        ],
        ResearchLevel.L2: [
            DecomposeStageImpl(llm_client, max_sub_questions=10),
            MultiSourceSearchStageImpl(search_engine, backends=["ddg", "scholar", "arxiv", "metaso", "exa", "brave", "zhipu"], max_results=25),
            EntityExtractionStageImpl(nlp_pipeline, llm_client, knowledge_store, nlp_zh=nlp_pipeline_zh),
            DeepReadStageImpl(search_engine, long_context, top_n=15),
            CrossAnalyzeStageImpl(llm_client),
            QualityGateStageImpl(),
            OutputStageImpl(llm_client=llm_client, knowledge_store=knowledge_store),
        ],
        ResearchLevel.L3: [
            DecomposeStageImpl(llm_client, max_sub_questions=15),
            MultiSourceSearchStageImpl(search_engine, backends=["ddg", "scholar", "arxiv", "metaso", "exa", "brave", "zhipu"], max_results=35),
            EntityExtractionStageImpl(nlp_pipeline, llm_client, knowledge_store, nlp_zh=nlp_pipeline_zh),
            DeepReadStageImpl(search_engine, long_context, top_n=20),
            CrossAnalyzeStageImpl(reasoner),
            CounterArgumentStageImpl(reasoner),
            QualityGateStageImpl(),
            OutputStageImpl(llm_client=llm_client, knowledge_store=knowledge_store),
        ],
        ResearchLevel.L4: [
            DecomposeStageImpl(llm_client, max_sub_questions=15),
            MultiSourceSearchStageImpl(search_engine, backends=["ddg", "scholar", "arxiv", "metaso", "exa", "brave", "zhipu"], max_results=50),
            EntityExtractionStageImpl(nlp_pipeline, llm_client, knowledge_store, nlp_zh=nlp_pipeline_zh),
            DeepReadStageImpl(search_engine, long_context, top_n=25),
            CrossAnalyzeStageImpl(reasoner),
            CounterArgumentStageImpl(reasoner),
            MultiModelVotingStageImpl(reasoner),
            QualityGateStageImpl(),
            ExtendedOutputStageImpl(llm_client=llm_client, knowledge_store=knowledge_store),
        ],
    }

    return Pipeline(stages)
