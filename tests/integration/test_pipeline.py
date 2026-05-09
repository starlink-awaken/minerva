"""Integration tests for Minerva pipeline — L0 and L2 end-to-end."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from minerva.knowledge.store import SQLiteKnowledgeStore
from minerva.pipeline.engine import Pipeline, ResearchContext, ResearchLevel
from minerva.pipeline.stages import (
    DecomposeStageImpl as DecomposeStage,
    MultiSourceSearchStageImpl as MultiSourceSearchStage,
    EntityExtractionStageImpl as EntityExtractionStage,
    DeepReadStageImpl as DeepReadStage,
    CrossAnalyzeStageImpl as CrossAnalyzeStage,
    QualityGateStageImpl as QualityGateStage,
    OutputStageImpl as OutputStage,
)
from minerva.search.engine import SearchEngine
from minerva.triage.router import TriageRouter, TriageResult


@pytest.fixture
def mock_llm():
    """Mock LLM client that returns reasonable responses."""
    client = AsyncMock()
    client.generate.return_value = "Mock LLM response with analysis."
    return client


@pytest.fixture
def mock_search_engine():
    """Mock search engine with test results."""
    engine = MagicMock(spec=SearchEngine)
    from minerva.search.engine import SearchResult

    async def mock_search(query, backends=None, max_results=25):
        return [
            SearchResult(
                title=f"Result {i}: {query[:30]}",
                url=f"https://example.com/{i}",
                snippet=f"This is test snippet {i} about {query[:20]}",
                source="searxng" if i % 2 == 0 else "scholar",
                published_date="2026-01-01",
                rank_score=1.0 - i * 0.05,
            )
            for i in range(1, 8)
        ]

    engine.search = mock_search
    engine.extract_content = AsyncMock(return_value="Extracted content for analysis.")
    return engine


@pytest.fixture
def knowledge_store():
    """In-memory knowledge store for testing."""
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = SQLiteKnowledgeStore(db_path=path)
    yield store
    store.conn.close()
    os.unlink(path)


@pytest.fixture
def pipeline(mock_llm, mock_search_engine):
    """Create a minimal L0 pipeline for testing."""
    stages = [
        MultiSourceSearchStage(mock_search_engine, backends=["searxng", "scholar"], max_results=10),
        OutputStage(llm_client=mock_llm),
    ]
    return Pipeline({ResearchLevel.L0: stages})


class TestIntegrationPipeline:
    """Integration tests for the research pipeline."""


    @pytest.mark.asyncio
    async def test_l0_e2e(self, pipeline, mock_llm, mock_search_engine):
        """Test L0 pipeline end-to-end with mocked services."""
        triage = TriageResult(
            level=ResearchLevel.L0,
            scores={"domain_complexity": 2, "timeliness": 2, "depth_required": 2,
                    "multi_source": 2, "privacy_sensitivity": 1},
            cost_estimate=0.0,
            model_plan={"agent": "test-model"},
            search_plan=["searxng"],
        )

        ctx = await pipeline.run(
            query="What is Python asyncio?",
            level=ResearchLevel.L0,
            triage=triage,
        )

        assert ctx.report is not None, "L0 should produce a report"
        assert ctx.report_path is not None, "L0 should write report to disk"
        assert len(ctx.search_results) >= 3, "L0 should have search results"
        assert "python" in ctx.report.lower() or "Python" in ctx.report, "Report should mention the query topic"
        assert ctx.cost == 0.0, "L0 should be free"

    @pytest.mark.asyncio
    async def test_l2_e2e(self, mock_llm, mock_search_engine):
        """Test L2 pipeline end-to-end with mocked services."""
        stages = [
            DecomposeStage(mock_llm, max_sub_questions=3),
            MultiSourceSearchStage(mock_search_engine, backends=["searxng", "scholar"], max_results=25),
            EntityExtractionStage(None, mock_llm),  # None NLP = skip spaCy
            DeepReadStage(mock_search_engine, mock_llm, top_n=5),
            CrossAnalyzeStage(mock_llm),
            QualityGateStage(),
            OutputStage(llm_client=mock_llm),
        ]
        pipeline = Pipeline({ResearchLevel.L2: stages})

        triage = TriageResult(
            level=ResearchLevel.L2,
            scores={"domain_complexity": 3, "timeliness": 2, "depth_required": 4,
                    "multi_source": 3, "privacy_sensitivity": 1},
            cost_estimate=0.30,
            model_plan={"agent": "qwen3:30b-a3b"},
            search_plan=["searxng", "scholar"],
        )

        ctx = await pipeline.run(
            query="Analyze the evolution of transformer architecture in NLP",
            level=ResearchLevel.L2,
            triage=triage,
        )

        assert ctx.report is not None, "L2 should produce a report"
        assert ctx.report_path is not None, "L2 should write report to disk"
        assert len(ctx.search_results) >= 5, f"L2 should have >=5 citations, got {len(ctx.search_results)}"
        assert "http" in ctx.report, "Report should contain URLs (citations)"
