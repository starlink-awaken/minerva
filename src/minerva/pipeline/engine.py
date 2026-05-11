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
# Stage Implementations
# ============================================================

class DecomposeStage(IPipelineStage):
    """Decompose query into sub-questions using local LLM."""

    name = "decompose"

    def __init__(self, llm_client, max_sub_questions: int = 5):
        self.llm = llm_client
        self.max_sub = max_sub_questions

    async def execute(self, ctx: ResearchContext) -> ResearchContext:
        """
        Pseudocode:
        1. Send ctx.query to LLM with DECOMPOSE_PROMPT
        2. Parse response into list of sub-questions
        3. ctx.sub_questions = ["Q1: ...", "Q2: ...", ...]
        4. Return ctx
        """
        ...
        return ctx


class MultiSourceSearchStage(IPipelineStage):
    """Parallel search across multiple backends."""

    name = "search"

    def __init__(self, search_engine, backends: list[str], max_results: int = 25):
        self.search_engine = search_engine
        self.backends = backends
        self.max_results = max_results

    async def execute(self, ctx: ResearchContext) -> ResearchContext:
        """
        Pseudocode:
        1. For each sub_question in ctx.sub_questions:
           a. Dispatch parallel search to all backends:
              - SearXNG (local, free)
              - Exa API (if enabled and within budget)
              - Semantic Scholar (academic)
              - 秘塔AI搜索 (Chinese content)
           b. Collect results, deduplicate by URL
        2. Rank by RRF fusion of all backends
        3. ctx.search_results = top-N results with snippets
        4. ctx.cost += search API costs
        5. Return ctx
        """
        ...
        return ctx


class EntityExtractionStage(IPipelineStage):
    """Extract entities using spaCy NLP + LLM fallback."""

    name = "entity_extraction"

    def __init__(self, nlp_pipeline, llm_client):
        self.nlp = nlp_pipeline  # spaCy
        self.llm = llm_client

    async def execute(self, ctx: ResearchContext) -> ResearchContext:
        """
        Pseudocode:
        1. For each search result snippet:
           a. Run spaCy NER → entities with confidence
           b. For low-confidence entities (< 0.7):
              - Send to Qwen3.6-35B for confirmation
              - Only 5% of entities typically need LLM confirmation
           c. Classify entities into ontology types (Person/Org/Product/...)
        2. Upsert entities to KnowledgeStore
        3. ctx.entities = extracted entities
        4. ctx.cost += LLM confirmation costs (minimal)
        5. Return ctx
        """
        ...
        return ctx


class DeepReadStage(IPipelineStage):
    """Extract full content and cross-analyze with large-context model."""

    name = "deep_read"

    def __init__(self, content_extractor, llm_client, top_n: int = 15):
        self.extractor = content_extractor
        self.llm = llm_client  # V4-Flash for 1M context
        self.top_n = top_n

    async def execute(self, ctx: ResearchContext) -> ResearchContext:
        """
        Pseudocode:
        1. Filter search_results by relevance, take top top_n
        2. Extract full text for each URL (Jina Reader or BeautifulSoup)
        3. Concatenate all into single document
        4. Send to V4-Flash (1M context) with DEEP_READ_PROMPT:
           a. Extract key claims from each source
           b. Mark consensus points (all sources agree)
           c. Mark contradictions (source A says X, source B says non-X)
           d. Mark gaps (no source discusses Z)
           e. Mark evolution relationships (B builds on A, C refutes B)
        5. ctx.extracted_content = full texts
        6. Store analysis in ctx.contradictions
        7. ctx.cost += V4-Flash API cost (~$0.05-0.15)
        8. Return ctx
        """
        ...
        return ctx


class CrossAnalyzeStage(IPipelineStage):
    """Deep reasoning analysis using local R1-70B."""

    name = "cross_analyze"

    def __init__(self, llm_client):
        self.llm = llm_client  # DeepSeek-R1-70B

    async def execute(self, ctx: ResearchContext) -> ResearchContext:
        """
        Pseudocode:
        1. Compile analysis matrix from DeepReadStage:
           - For each contradiction: which claim is more credible? Why?
           - For each gap: is it unexplored or unsolvable?
           - For evolution: what's the likely next step?
        2. Send to DeepSeek-R1-70B (local, CoT reasoning)
        3. R1 produces structured reasoning chains + confidence scores
        4. Extract new relations (SUPPORTS, CONTRADICTS, IMPROVES, OBSOLETES)
        5. Upsert relations to KnowledgeStore
        6. ctx.relations = new relations
        7. Return ctx
        """
        ...
        return ctx


class QualityGateStage(IPipelineStage):
    """Verify research quality before output."""

    name = "quality_gate"

    async def execute(self, ctx: ResearchContext) -> ResearchContext:
        """
        Pseudocode:
        Checks (all must pass):
        1. Every key claim has ≥1 traceable source? → □
        2. No "studies show" without specific citation? → □
        3. Contradictions are explicitly noted, not hidden? → □
        4. Confidence levels assigned to major conclusions? → □
        5. Report structure complete (summary + findings + evidence + gaps)? → □

        If any check fails → raise QualityGateFailure
        → Pipeline retries from DeepReadStage with broader sources

        If all pass → ctx can proceed to OutputStage
        """
        ...
        return ctx


class OutputStage(IPipelineStage):
    """Generate final report and update knowledge base."""

    name = "output"

    def __init__(self, llm_client, knowledge_store, creative_tool=None):
        self.llm = llm_client  # Qwen3.5-122B for long-form writing
        self.kb = knowledge_store
        self.creative = creative_tool  # Optional: NotebookLM adapter

    async def execute(self, ctx: ResearchContext) -> ResearchContext:
        """
        Pseudocode:
        1. Compile all context into structured prompt
        2. Send to Qwen3.5-122B with REPORT_TEMPLATE:
           a. Executive Summary (200 words)
           b. Key Findings (5-8, each with confidence)
           c. Evidence Matrix (table)
           d. Contradictions & Disputes (with source positions)
           e. Evolution Timeline (Mermaid)
           f. Gaps & Opportunities
           g. Full Citation List (clickable URLs)
        3. Write report to ~/knowledge/reports/{date}_{slug}.md
        4. Optionally: generate NotebookLM mind map + audio overview
        5. Update knowledge base:
           - New entities → KnowledgeStore
           - New relations → KnowledgeStore
           - Report metadata → knowledge index
        6. ctx.report = report content
        7. ctx.report_path = file path
        8. Return ctx
        """
        ...
        return ctx


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
) -> Pipeline:
    """Create pipeline with default stage configurations for each level."""

    from minerva.pipeline.stages import (
        DecomposeStageImpl,
        MultiSourceSearchStageImpl,
        EntityExtractionStageImpl,
        DeepReadStageImpl,
        CrossAnalyzeStageImpl,
        QualityGateStageImpl,
        OutputStageImpl,
        CounterArgumentStageImpl,
        MultiModelVotingStageImpl,
        ExtendedOutputStageImpl,
    )

    stages = {
        ResearchLevel.L0: [
            MultiSourceSearchStageImpl(search_engine, backends=["ddg", "scholar", "metaso", "exa"], max_results=5),
            OutputStageImpl(llm_client=llm_client, knowledge_store=knowledge_store),
        ],
        ResearchLevel.L1: [
            DecomposeStageImpl(llm_client, max_sub_questions=5),
            MultiSourceSearchStageImpl(search_engine, backends=["ddg", "scholar", "metaso", "exa"], max_results=10),
            CrossAnalyzeStageImpl(llm_client),
            OutputStageImpl(llm_client=llm_client, knowledge_store=knowledge_store),
        ],
        ResearchLevel.L2: [
            DecomposeStageImpl(llm_client, max_sub_questions=10),
            MultiSourceSearchStageImpl(search_engine, backends=["ddg", "scholar", "arxiv", "metaso", "exa"], max_results=25),
            EntityExtractionStageImpl(nlp_pipeline, llm_client, knowledge_store, nlp_zh=nlp_pipeline_zh),
            DeepReadStageImpl(search_engine, llm_client, top_n=15),
            CrossAnalyzeStageImpl(llm_client),
            QualityGateStageImpl(),
            OutputStageImpl(llm_client=llm_client, knowledge_store=knowledge_store),
        ],
        ResearchLevel.L3: [
            DecomposeStageImpl(llm_client, max_sub_questions=15),
            MultiSourceSearchStageImpl(search_engine, backends=["ddg", "scholar", "arxiv", "metaso", "exa"], max_results=35),
            EntityExtractionStageImpl(nlp_pipeline, llm_client, knowledge_store, nlp_zh=nlp_pipeline_zh),
            DeepReadStageImpl(search_engine, llm_client, top_n=20),
            CrossAnalyzeStageImpl(llm_client),
            CounterArgumentStageImpl(llm_client),
            QualityGateStageImpl(),
            OutputStageImpl(llm_client=llm_client, knowledge_store=knowledge_store),
        ],
        ResearchLevel.L4: [
            DecomposeStageImpl(llm_client, max_sub_questions=15),
            MultiSourceSearchStageImpl(search_engine, backends=["ddg", "scholar", "arxiv", "metaso", "exa"], max_results=50),
            EntityExtractionStageImpl(nlp_pipeline, llm_client, knowledge_store, nlp_zh=nlp_pipeline_zh),
            DeepReadStageImpl(search_engine, llm_client, top_n=25),
            CrossAnalyzeStageImpl(llm_client),
            CounterArgumentStageImpl(llm_client),
            MultiModelVotingStageImpl(llm_client),
            QualityGateStageImpl(),
            ExtendedOutputStageImpl(llm_client=llm_client, knowledge_store=knowledge_store),
        ],
    }

    return Pipeline(stages)
