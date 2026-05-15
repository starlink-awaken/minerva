"""Unit tests for all pipeline stage implementations in minerva.pipeline.stages."""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock

from minerva.pipeline.engine import QualityGateFailure, ResearchContext
from minerva.triage.router import ResearchLevel, TriageResult


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_triage(level: ResearchLevel = ResearchLevel.L2) -> TriageResult:
    """Create a minimal TriageResult for testing."""
    return TriageResult(
        level=level,
        scores={"domain_complexity": 3, "timeliness": 2, "depth_required": 4,
                "multi_source": 3, "privacy_sensitivity": 1},
        cost_estimate=0.30,
        model_plan={"reasoner": "local"},
        search_plan=["web_search"],
    )


def _make_ctx(
    query: str = "test query",
    level: ResearchLevel = ResearchLevel.L2,
    search_results: list[dict] | None = None,
    entities: list[dict] | None = None,
    contradictions: list[dict] | None = None,
    relations: list[dict] | None = None,
    sub_questions: list[str] | None = None,
    cost: float = 0.0,
) -> ResearchContext:
    """Create a ResearchContext with optional pre-populated fields."""
    return ResearchContext(
        query=query,
        level=level,
        triage=_make_triage(level),
        search_results=search_results or [],
        entities=entities or [],
        contradictions=contradictions or [],
        relations=relations or [],
        sub_questions=sub_questions or [],
        cost=cost,
    )


def _make_search_result(
    title: str = "Test Result",
    url: str = "https://example.com",
    snippet: str = "A test snippet.",
    source: str = "web",
    published_date: str = "2024-01-01",
    rank_score: float = 0.9,
) -> dict:
    """Create a search result dict matching the shape produced by search stages."""
    return {
        "title": title,
        "url": url,
        "snippet": snippet,
        "source": source,
        "published_date": published_date,
        "rank_score": rank_score,
    }


def _make_spacy_ent(label: str, text: str) -> MagicMock:
    """Create a MagicMock that behaves like a spaCy Span entity."""
    ent = MagicMock()
    ent.label_ = label
    ent.text = text
    return ent


def _make_spacy_doc(*ents: MagicMock) -> MagicMock:
    """Create a MagicMock that behaves like a spaCy Doc with given entities."""
    doc = MagicMock()
    doc.ents = list(ents)
    return doc


# ===================================================================
# DecomposeStageImpl
# ===================================================================

class TestDecomposeStageImpl:
    """Tests for DecomposeStageImpl — query decomposition into sub-questions."""

    @pytest.mark.asyncio
    async def test_decomposes_query_into_sub_questions(self):
        """Decompose should parse LLM response lines into ctx.sub_questions."""
        from minerva.pipeline.stages import DecomposeStageImpl

        llm = AsyncMock()
        llm.generate.return_value = (
            "- What is the first aspect?\n"
            "- What is the second aspect?\n"
            "- Third sub question here.\n"
        )

        stage = DecomposeStageImpl(llm, max_sub_questions=5)
        ctx = _make_ctx(query="What is MoE?")

        result = await stage.execute(ctx)

        assert len(result.sub_questions) == 3
        assert "What is the first aspect?" in result.sub_questions
        assert "What is the second aspect?" in result.sub_questions
        assert "Third sub question here." in result.sub_questions
        assert llm.generate.call_count >= 1  # deep_read + optional verifier

    @pytest.mark.asyncio
    async def test_falls_back_to_original_query_on_exception(self):
        """On LLM failure, sub_questions should be [ctx.query]."""
        from minerva.pipeline.stages import DecomposeStageImpl

        llm = AsyncMock()
        llm.generate.side_effect = RuntimeError("LLM unavailable")

        stage = DecomposeStageImpl(llm, max_sub_questions=5)
        ctx = _make_ctx(query="What is MoE?")

        result = await stage.execute(ctx)

        assert result.sub_questions == ["What is MoE?"]

    @pytest.mark.asyncio
    async def test_limits_to_max_sub_questions(self):
        """Should truncate sub-questions list to max_sub_questions."""
        from minerva.pipeline.stages import DecomposeStageImpl

        llm = AsyncMock()
        llm.generate.return_value = "\n".join(f"- Question {i}" for i in range(10))

        stage = DecomposeStageImpl(llm, max_sub_questions=3)
        ctx = _make_ctx(query="test")

        result = await stage.execute(ctx)

        assert len(result.sub_questions) == 3
        assert result.sub_questions == [f"Question {i}" for i in range(3)]

    @pytest.mark.asyncio
    async def test_filters_short_and_empty_lines(self):
        """Lines shorter than 6 characters after stripping should be ignored."""
        from minerva.pipeline.stages import DecomposeStageImpl

        llm = AsyncMock()
        llm.generate.return_value = (
            "- Valid question here?\n"
            "  \n"
            "- X\n"          # too short (after strip: "X", len=1)
            "- Another valid question.\n"
        )

        stage = DecomposeStageImpl(llm, max_sub_questions=5)
        ctx = _make_ctx(query="test")

        result = await stage.execute(ctx)

        assert len(result.sub_questions) == 2
        assert "X" not in result.sub_questions


# ===================================================================
# MultiSourceSearchStageImpl
# ===================================================================

class TestMultiSourceSearchStageImpl:
    """Tests for MultiSourceSearchStageImpl — parallel multi-backend search."""

    @pytest.mark.asyncio
    async def test_searches_each_sub_question(self):
        """Should call search_engine.search() for each sub-question."""
        from minerva.pipeline.stages import MultiSourceSearchStageImpl

        r1 = MagicMock()
        r1.title = "R1"; r1.url = "http://a.com"; r1.snippet = "S1"
        r1.source = "web"; r1.published_date = "2024-01-01"; r1.rank_score = 0.9

        r2 = MagicMock()
        r2.title = "R2"; r2.url = "http://b.com"; r2.snippet = "S2"
        r2.source = "scholar"; r2.published_date = "2024-02-01"; r2.rank_score = 0.8

        search_engine = MagicMock()
        search_engine.search = AsyncMock(side_effect=[[r1], [r2]])

        stage = MultiSourceSearchStageImpl(
            search_engine, backends=["ddg", "scholar"], max_results=10
        )
        ctx = _make_ctx(sub_questions=["Q1", "Q2"])

        result = await stage.execute(ctx)

        assert search_engine.search.call_count == 2
        # First call (i=0) uses max_results=10, subsequent calls use 5
        assert search_engine.search.call_args_list[0][1]["max_results"] == 10
        assert search_engine.search.call_args_list[1][1]["max_results"] == 5
        assert len(result.search_results) == 2
        assert result.search_results[0]["title"] == "R1"
        assert result.search_results[1]["title"] == "R2"

    @pytest.mark.asyncio
    async def test_falls_back_to_query_when_no_sub_questions(self):
        """When ctx.sub_questions is empty, search with ctx.query."""
        from minerva.pipeline.stages import MultiSourceSearchStageImpl

        r = MagicMock()
        r.title = "Solo"; r.url = "http://solo.com"; r.snippet = "S"
        r.source = "web"; r.published_date = "2024-01-01"; r.rank_score = 0.5

        search_engine = MagicMock()
        search_engine.search = AsyncMock(return_value=[r])

        stage = MultiSourceSearchStageImpl(
            search_engine, backends=["ddg"], max_results=10
        )
        ctx = _make_ctx(query="fallback query", sub_questions=[])

        result = await stage.execute(ctx)

        search_engine.search.assert_called_once()
        assert search_engine.search.call_args[0][0] == "fallback query"

    @pytest.mark.asyncio
    async def test_deduplicates_by_url(self):
        """Results with the same URL should only appear once."""
        from minerva.pipeline.stages import MultiSourceSearchStageImpl

        r1 = MagicMock()
        r1.title = "Dup A"; r1.url = "http://dup.com"; r1.snippet = "S1"
        r1.source = "ddg"; r1.published_date = "2024-01-01"; r1.rank_score = 0.9

        r2 = MagicMock()
        r2.title = "Dup B"; r2.url = "http://dup.com"; r2.snippet = "S2"
        r2.source = "brave"; r2.published_date = "2024-01-02"; r2.rank_score = 0.8

        search_engine = MagicMock()
        search_engine.search = AsyncMock(side_effect=[[r1, r2]])

        stage = MultiSourceSearchStageImpl(
            search_engine, backends=["ddg", "brave"], max_results=10
        )
        ctx = _make_ctx(sub_questions=["Q1"])

        result = await stage.execute(ctx)

        assert len(result.search_results) == 1
        assert result.search_results[0]["title"] == "Dup A"

    @pytest.mark.asyncio
    async def test_handles_search_exceptions_gracefully(self):
        """Individual search failures should not block other results."""
        from minerva.pipeline.stages import MultiSourceSearchStageImpl

        r = MagicMock()
        r.title = "Good"; r.url = "http://good.com"; r.snippet = "OK"
        r.source = "web"; r.published_date = "2024-01-01"; r.rank_score = 0.5

        search_engine = MagicMock()
        search_engine.search = AsyncMock(side_effect=[
            RuntimeError("Backend failed"),
            [r],
        ])

        stage = MultiSourceSearchStageImpl(
            search_engine, backends=["ddg"], max_results=10
        )
        ctx = _make_ctx(sub_questions=["Q1", "Q2"])

        result = await stage.execute(ctx)

        assert len(result.search_results) == 1
        assert result.search_results[0]["title"] == "Good"


# ===================================================================
# EntityExtractionStageImpl
# ===================================================================

class TestEntityExtractionStageImpl:
    """Tests for EntityExtractionStageImpl — spaCy NER + KB upsert."""

    @pytest.mark.asyncio
    async def test_extracts_entities_from_search_results(self):
        """Should run spaCy NER on first 10 snippets and populate ctx.entities."""
        from minerva.pipeline.stages import EntityExtractionStageImpl

        org_ent = _make_spacy_ent("ORG", "OpenAI")
        person_ent = _make_spacy_ent("PERSON", "Ilya Sutskever")
        mock_doc = _make_spacy_doc(org_ent, person_ent)
        mock_nlp = MagicMock(return_value=mock_doc)

        stage = EntityExtractionStageImpl(
            nlp_pipeline=mock_nlp, llm_client=AsyncMock(),
            knowledge_store=None, nlp_zh=None,
        )
        ctx = _make_ctx(search_results=[
            _make_search_result(snippet="OpenAI was founded by Ilya Sutskever."),
            _make_search_result(snippet="Another result."),
        ])

        result = await stage.execute(ctx)

        assert len(result.entities) >= 2
        entity_types = {e["type"] for e in result.entities}
        assert "Organization" in entity_types
        assert "Person" in entity_types
        entity_names = {e["name"] for e in result.entities}
        assert "OpenAI" in entity_names
        assert "Ilya Sutskever" in entity_names

    @pytest.mark.asyncio
    async def test_skips_empty_snippets(self):
        """Results with empty title AND snippet should not cause NER processing."""
        from minerva.pipeline.stages import EntityExtractionStageImpl

        mock_doc = _make_spacy_doc()
        mock_nlp = MagicMock(return_value=mock_doc)

        stage = EntityExtractionStageImpl(
            nlp_pipeline=mock_nlp, llm_client=AsyncMock(),
        )
        ctx = _make_ctx(search_results=[
            _make_search_result(title="", snippet=""),
            _make_search_result(snippet="Valid snippet text here."),
        ])

        result = await stage.execute(ctx)

        # Only one call — empty title+snippet skipped, non-empty processed
        assert mock_nlp.call_count == 1

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_nlp_pipeline(self):
        """When nlp_pipeline is None, entities should be empty."""
        from minerva.pipeline.stages import EntityExtractionStageImpl

        stage = EntityExtractionStageImpl(
            nlp_pipeline=None, llm_client=AsyncMock(),
        )
        ctx = _make_ctx(search_results=[_make_search_result()])

        result = await stage.execute(ctx)

        assert result.entities == []

    @pytest.mark.asyncio
    async def test_upserts_entities_to_knowledge_store(self):
        """When knowledge_store is provided, each entity should be upserted."""
        from minerva.pipeline.stages import EntityExtractionStageImpl

        org_ent = _make_spacy_ent("ORG", "DeepMind")
        mock_doc = _make_spacy_doc(org_ent)
        mock_nlp = MagicMock(return_value=mock_doc)
        mock_kb = MagicMock()
        mock_kb.upsert_entity = AsyncMock()

        stage = EntityExtractionStageImpl(
            nlp_pipeline=mock_nlp, llm_client=AsyncMock(),
            knowledge_store=mock_kb,
        )
        ctx = _make_ctx(search_results=[
            _make_search_result(snippet="DeepMind is an AI company."),
        ])

        await stage.execute(ctx)

        mock_kb.upsert_entity.assert_called_once()
        upserted_entity = mock_kb.upsert_entity.call_args[0][0]
        assert upserted_entity.name == "DeepMind"
        assert upserted_entity.type == "Organization"

    def test_detect_language_english(self):
        """English text should be detected as 'en'."""
        from minerva.pipeline.stages import EntityExtractionStageImpl

        stage = EntityExtractionStageImpl(
            nlp_pipeline=MagicMock(), llm_client=AsyncMock(),
        )
        assert stage._detect_language("This is English text about AI.") == "en"

    def test_detect_language_chinese(self):
        """Chinese text should be detected as 'zh'."""
        from minerva.pipeline.stages import EntityExtractionStageImpl

        stage = EntityExtractionStageImpl(
            nlp_pipeline=MagicMock(), llm_client=AsyncMock(),
        )
        assert stage._detect_language("这是一段中文测试文本内容") == "zh"

    def test_detect_language_mixed_below_threshold(self):
        """Text with very few CJK characters (<5%) should be 'en'."""
        from minerva.pipeline.stages import EntityExtractionStageImpl

        stage = EntityExtractionStageImpl(
            nlp_pipeline=MagicMock(), llm_client=AsyncMock(),
        )
        long_enough = "This is a very long English sentence with only one CJK character 中"
        assert stage._detect_language(long_enough) == "en"

    def test_detect_language_mixed_above_threshold(self):
        """Text with CJK characters exceeding 5% threshold should be 'zh'."""
        from minerva.pipeline.stages import EntityExtractionStageImpl

        stage = EntityExtractionStageImpl(
            nlp_pipeline=MagicMock(), llm_client=AsyncMock(),
        )
        # 2 CJK chars out of 16 total = 12.5%
        assert stage._detect_language("Mixed Chinese 中文") == "zh"


# ===================================================================
# DeepReadStageImpl
# ===================================================================

class TestDeepReadStageImpl:
    """Tests for DeepReadStageImpl — content extraction + LLM analysis."""

    @pytest.mark.asyncio
    async def test_extracts_content_and_sends_to_llm(self):
        """Should extract content from top_n results and send to LLM for analysis."""
        from minerva.pipeline.stages import DeepReadStageImpl

        extractor = MagicMock()
        extractor.extract_content = AsyncMock(return_value="Full document content here.")

        llm = AsyncMock()
        llm.generate.return_value = "Analysis of documents."

        stage = DeepReadStageImpl(extractor, llm, top_n=3)
        ctx = _make_ctx(search_results=[
            _make_search_result(url="http://a.com", title="Doc A"),
            _make_search_result(url="http://b.com", title="Doc B"),
            _make_search_result(url="http://c.com", title="Doc C"),
        ])

        result = await stage.execute(ctx)

        assert extractor.extract_content.call_count == 3
        assert llm.generate.call_count >= 1  # deep_read + optional verifier
        assert len(result.extracted_content) == 3
        assert len(result.contradictions) == 1
        assert result.contradictions[0]["analysis"] == "Analysis of documents."

    @pytest.mark.asyncio
    async def test_handles_empty_search_results(self):
        """When no search results, extracted_content should be empty."""
        from minerva.pipeline.stages import DeepReadStageImpl

        extractor = MagicMock()
        llm = AsyncMock()
        stage = DeepReadStageImpl(extractor, llm, top_n=15)
        ctx = _make_ctx(search_results=[])

        result = await stage.execute(ctx)

        assert result.extracted_content == []
        extractor.extract_content.assert_not_called()
        llm.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_llm_exception_gracefully(self):
        """When LLM fails, a fallback message should be stored."""
        from minerva.pipeline.stages import DeepReadStageImpl

        extractor = MagicMock()
        extractor.extract_content = AsyncMock(return_value="Some content.")

        llm = AsyncMock()
        llm.generate.side_effect = RuntimeError("LLM down")

        stage = DeepReadStageImpl(extractor, llm, top_n=3)
        ctx = _make_ctx(search_results=[
            _make_search_result(url="http://a.com", title="Doc A"),
        ])

        result = await stage.execute(ctx)

        assert len(result.extracted_content) == 1
        assert result.contradictions[0]["analysis"] == "Deep read analysis unavailable."

    @pytest.mark.asyncio
    async def test_skips_results_with_no_url(self):
        """Results without a URL should be skipped for content extraction."""
        from minerva.pipeline.stages import DeepReadStageImpl

        extractor = MagicMock()
        extractor.extract_content = AsyncMock(return_value="Content.")
        llm = AsyncMock()
        llm.generate.return_value = "OK"

        stage = DeepReadStageImpl(extractor, llm, top_n=5)
        ctx = _make_ctx(search_results=[
            _make_search_result(url="", title="No URL"),
            _make_search_result(url="http://valid.com", title="Has URL"),
        ])

        result = await stage.execute(ctx)

        # Only the second result (with URL) should trigger extraction
        assert extractor.extract_content.call_count == 1
        assert extractor.extract_content.call_args[0][0] == "http://valid.com"


# ===================================================================
# CrossAnalyzeStageImpl
# ===================================================================

class TestCrossAnalyzeStageImpl:
    """Tests for CrossAnalyzeStageImpl — deep reasoning on contradictions."""

    @pytest.mark.asyncio
    async def test_analyzes_contradictions(self):
        """Should aggregate contradiction analyses and send for deep reasoning."""
        from minerva.pipeline.stages import CrossAnalyzeStageImpl

        llm = AsyncMock()
        llm.generate.return_value = "Deep reasoning result."

        stage = CrossAnalyzeStageImpl(llm)
        ctx = _make_ctx(query="What is AGI?", contradictions=[
            {"analysis": "Source A claims X."},
            {"analysis": "Source B refutes X."},
        ])

        result = await stage.execute(ctx)

        assert llm.generate.call_count >= 1  # deep_read + optional verifier
        assert len(result.relations) == 1
        assert result.relations[0]["reasoning"] == "Deep reasoning result."

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_contradictions(self):
        """When no contradiction analysis exists, relations should stay empty."""
        from minerva.pipeline.stages import CrossAnalyzeStageImpl

        llm = AsyncMock()
        stage = CrossAnalyzeStageImpl(llm)
        ctx = _make_ctx(contradictions=[])

        result = await stage.execute(ctx)

        assert result.relations == []
        llm.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_llm_exception_gracefully(self):
        """When LLM fails, a fallback message should be stored."""
        from minerva.pipeline.stages import CrossAnalyzeStageImpl

        llm = AsyncMock()
        llm.generate.side_effect = RuntimeError("LLM down")

        stage = CrossAnalyzeStageImpl(llm)
        ctx = _make_ctx(contradictions=[{"analysis": "Some analysis text."}])

        result = await stage.execute(ctx)

        assert len(result.relations) == 1
        assert result.relations[0]["reasoning"] == "Cross-analysis unavailable."


# ===================================================================
# QualityGateStageImpl
# ===================================================================

class TestQualityGateStageImpl:
    """Tests for QualityGateStageImpl — research quality scoring."""

    @pytest.mark.asyncio
    async def test_passes_with_good_quality(self):
        """Should assign score 100 when all quality checks pass."""
        from minerva.pipeline.stages import QualityGateStageImpl

        stage = QualityGateStageImpl()
        ctx = _make_ctx(
            search_results=[
                _make_search_result(source="scholar"),
                _make_search_result(source="web"),
                _make_search_result(source="ddg"),
                _make_search_result(source="brave"),
                _make_search_result(source="exa"),
            ],
            entities=[{"id": "e1", "type": "Person", "name": "X"}],
            contradictions=[{"analysis": "x" * 60}],
        )

        result = await stage.execute(ctx)

        assert len(result.relations) == 1
        assert result.relations[0]["quality_score"] == 100
        assert result.relations[0]["quality_gate_checks"]["source_count"] == 5
        assert result.relations[0]["quality_gate_checks"]["entity_count"] == 1
        assert result.relations[0]["failures"] == []

    @pytest.mark.asyncio
    async def test_fails_with_no_search_results(self):
        """Zero search results should trigger QualityGateFailure with score 0."""
        from minerva.pipeline.stages import QualityGateStageImpl

        stage = QualityGateStageImpl()
        ctx = _make_ctx(search_results=[])

        with pytest.raises(QualityGateFailure) as exc_info:
            await stage.execute(ctx)

        assert "No search results found" in str(exc_info.value)
        assert "No search results found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fails_with_insufficient_sources_under_3(self):
        """Fewer than 3 sources should deduct 30 points and raise failure."""
        from minerva.pipeline.stages import QualityGateStageImpl

        stage = QualityGateStageImpl()
        ctx = _make_ctx(search_results=[
            _make_search_result(source="web"),
            _make_search_result(source="web"),
        ])

        with pytest.raises(QualityGateFailure) as exc_info:
            await stage.execute(ctx)

        assert "Insufficient sources" in str(exc_info.value)
        assert "Insufficient sources" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_deducts_for_few_sources_under_5(self):
        """3-4 sources should deduct 10 points but not fail if other checks pass."""
        from minerva.pipeline.stages import QualityGateStageImpl

        stage = QualityGateStageImpl()
        ctx = _make_ctx(
            search_results=[
                _make_search_result(source="web"),
                _make_search_result(source="scholar"),
                _make_search_result(source="ddg"),
            ],
            entities=[{"id": "e1", "type": "Org"}],
            contradictions=[{"analysis": "x" * 60}],
        )

        result = await stage.execute(ctx)

        assert result.relations[0]["quality_score"] <= 90

    @pytest.mark.asyncio
    async def test_deducts_for_no_entities(self):
        """Missing entities should deduct 10 points."""
        from minerva.pipeline.stages import QualityGateStageImpl

        stage = QualityGateStageImpl()
        ctx = _make_ctx(
            search_results=[
                _make_search_result(source="scholar"),
                _make_search_result(source="web"),
                _make_search_result(source="ddg"),
            ],
            entities=[],  # no entities
            contradictions=[{"analysis": "x" * 60}],
        )

        result = await stage.execute(ctx)

        assert result.relations[0]["quality_score"] <= 90  # deduction for no entities

    @pytest.mark.asyncio
    async def test_deducts_for_single_source_backend(self):
        """All results from a single backend should deduct 15 points."""
        from minerva.pipeline.stages import QualityGateStageImpl

        stage = QualityGateStageImpl()
        ctx = _make_ctx(
            search_results=[
                _make_search_result(source="web"),
                _make_search_result(source="web"),
                _make_search_result(source="web"),
                _make_search_result(source="web"),
                _make_search_result(source="web"),
            ],
            entities=[{"id": "e1", "type": "Org"}],
            contradictions=[{"analysis": "x" * 60}],
        )

        result = await stage.execute(ctx)

        assert result.relations[0]["quality_score"] == 85  # 100 - 15 single source

    @pytest.mark.asyncio
    async def test_deducts_for_empty_contradiction_analysis(self):
        """Contradictions without substantive analysis should deduct 10 points."""
        from minerva.pipeline.stages import QualityGateStageImpl

        stage = QualityGateStageImpl()
        ctx = _make_ctx(
            search_results=[
                _make_search_result(source="scholar"),
                _make_search_result(source="web"),
                _make_search_result(source="ddg"),
            ],
            entities=[{"id": "e1", "type": "Org"}],
            contradictions=[{"analysis": ""}, {"analysis": "short"}],  # both < 50
        )

        result = await stage.execute(ctx)

        # 100 - 10 (for missing substantive analysis) = 90
        assert result.relations[0]["quality_score"] <= 90


# ===================================================================
# OutputStageImpl helpers
# ===================================================================

class TestOutputStageImplHelpers:
    """Tests for OutputStageImpl helper methods."""

    @pytest.fixture
    def stage(self, tmp_path):
        """Create an OutputStageImpl with no LLM to simplify tests."""
        from minerva.pipeline.stages import OutputStageImpl
        return OutputStageImpl(llm_client=None, knowledge_store=None, report_dir=str(tmp_path))

    def test_get_quality_score_from_relations(self, stage):
        """Should extract quality_score from relations list."""
        ctx = _make_ctx(relations=[{"quality_score": 85}])
        assert stage._get_quality_score(ctx) == "85"

    def test_get_quality_score_default(self, stage):
        """Should return 'N/A' when no quality_score in relations."""
        ctx = _make_ctx(relations=[])
        assert stage._get_quality_score(ctx) == "N/A"

    def test_source_conf_known_backends(self, stage):
        """Should map known source names to confidence levels."""
        assert stage._source_conf("scholar") == "HIGH"
        assert stage._source_conf("arxiv") == "HIGH"
        assert stage._source_conf("exa") == "MEDIUM-HIGH"
        assert stage._source_conf("web") == "MEDIUM"
        assert stage._source_conf("ddg") == "MEDIUM"

    def test_source_conf_unknown_backend(self, stage):
        """Unknown source names should default to MEDIUM."""
        assert stage._source_conf("random_xyz") == "MEDIUM"

    def test_build_filename(self, stage):
        """Should return timestamp and slug tuple."""
        ts, slug = stage._build_filename(
            _make_ctx(query="What Is Machine Learning?")
        )
        assert ts  # timestamp exists
        assert slug == "what-is-machine-learning?"  # truncated at 40, lowered, spaces→-

    def test_build_findings(self, stage):
        """Should format top N search results as numbered list."""
        ctx = _make_ctx(search_results=[
            _make_search_result(title="Result A", snippet="Snippet A content."),
            _make_search_result(title="Result B", snippet="Snippet B content."),
        ])
        findings = stage._build_findings(ctx, n=5)
        assert "1. **Result A**" in findings
        assert "2. **Result B**" in findings

    def test_build_findings_empty(self, stage):
        """Should return fallback message when no search results."""
        ctx = _make_ctx(search_results=[])
        assert stage._build_findings(ctx) == "No findings available."

    def test_build_evidence_rows(self, stage):
        """Should generate markdown table rows from search results."""
        ctx = _make_ctx(search_results=[
            _make_search_result(title="Evidence A", url="http://a.com", source="scholar"),
        ])
        rows = stage._build_evidence_rows(ctx, n=5)
        assert "Evidence A" in rows
        assert "http://a.com" in rows
        assert "HIGH" in rows  # scholar → HIGH

    def test_build_contradictions_with_analysis(self, stage):
        """Should return concatenated contradiction analyses."""
        ctx = _make_ctx(
            search_results=[_make_search_result(source="web")],
            contradictions=[
                {"analysis": "x" * 60},
                {"analysis": "y" * 60},
            ],
        )
        result = stage._build_contradictions(ctx)
        assert "x" * 60 in result
        assert "y" * 60 in result

    def test_build_contradictions_fallback(self, stage):
        """Should return consensus message when no substantive contradictions exist."""
        ctx = _make_ctx(
            search_results=[
                _make_search_result(source="scholar"),
                _make_search_result(source="web"),
            ],
            contradictions=[],
        )
        result = stage._build_contradictions(ctx)
        assert "No direct contradictions found" in result
        assert "2 sources" in result

    def test_build_gaps_missing_academic_sources(self, stage):
        """Should note missing academic sources when scholar/arxiv not present."""
        ctx = _make_ctx(search_results=[
            _make_search_result(source="web"),
            _make_search_result(source="ddg"),
        ])
        gaps = stage._build_gaps(ctx)
        assert "Academic sources" in gaps

    def test_build_gaps_limited_source_count(self, stage):
        """Should recommend re-running when source count is low."""
        ctx = _make_ctx(search_results=[
            _make_search_result(source="web"),
        ])
        gaps = stage._build_gaps(ctx)
        assert "Limited source count" in gaps

    def test_build_citations(self, stage):
        """Should generate numbered citation list with markdown links."""
        ctx = _make_ctx(search_results=[
            _make_search_result(
                title="Important Paper",
                url="https://doi.org/10.1234/example",
            ),
        ])
        citations = stage._build_citations(ctx, n=5)
        assert "1. [Important Paper]" in citations
        assert "https://doi.org/10.1234/example" in citations

    def test_generate_tldr(self, stage):
        """Should produce a 2-3 sentence TL;DR summary."""
        ctx = _make_ctx(
            search_results=[
                _make_search_result(title="Source One"),
                _make_search_result(title="Source Two"),
                _make_search_result(title="Source Three"),
            ],
            entities=[{"id": "e1"}],
            contradictions=[{"analysis": "x" * 60}],
        )
        tldr = stage._generate_tldr(ctx)
        assert "3 sources" in tldr
        assert "1 entities" in tldr
        assert "yes" in tldr  # contradictions found
        assert "Source One" in tldr

    @pytest.mark.asyncio
    async def test_execute_writes_report(self, tmp_path):
        """Execute should write EN report to disk and set ctx.report / ctx.report_path."""
        from minerva.pipeline.stages import OutputStageImpl

        stage = OutputStageImpl(
            llm_client=None,  # no LLM means no ZH translation
            knowledge_store=None,
            report_dir=str(tmp_path),
        )
        ctx = _make_ctx(
            query="Test Research",
            search_results=[
                _make_search_result(title="R1", source="web"),
                _make_search_result(title="R2", source="scholar"),
                _make_search_result(title="R3", source="ddg"),
            ],
            entities=[{"id": "e1", "type": "Person"}],
        )

        result = await stage.execute(ctx)

        assert result.report is not None
        assert "Test Research" in result.report
        assert result.report_path is not None
        assert result.report_path.endswith("_EN.md")
        # Verify file was actually written
        written = Path(result.report_path).read_text()
        assert "Test Research" in written

    @pytest.mark.asyncio
    async def test_execute_translates_to_chinese(self, tmp_path):
        """When LLM is available, _write_bilingual should create a ZH file."""
        from minerva.pipeline.stages import OutputStageImpl

        llm = AsyncMock()
        llm.generate.return_value = "这是翻译后的中文研究报告。"

        stage = OutputStageImpl(
            llm_client=llm,
            knowledge_store=None,
            report_dir=str(tmp_path),
        )
        ctx = _make_ctx(
            query="Test Research ZH",
            search_results=[
                _make_search_result(title="R1", source="web"),
                _make_search_result(title="R2", source="scholar"),
                _make_search_result(title="R3", source="ddg"),
            ],
        )

        result = await stage.execute(ctx)

        assert llm.generate.call_count >= 1  # deep_read + optional verifier
        # Should have zh_report_path in relations
        zh_paths = [
            r.get("zh_report_path")
            for r in (result.relations or [])
            if r.get("zh_report_path")
        ]
        assert len(zh_paths) == 1
        assert zh_paths[0].endswith("_ZH.md")
        # Verify ZH file exists
        assert Path(zh_paths[0]).exists()


# ===================================================================
# CounterArgumentStageImpl
# ===================================================================

class TestCounterArgumentStageImpl:
    """Tests for CounterArgumentStageImpl — devil's advocate analysis (L3+)."""

    @pytest.mark.asyncio
    async def test_generates_counter_arguments_from_contradictions(self):
        """Should send contradiction analysis to LLM and store counter argument."""
        from minerva.pipeline.stages import CounterArgumentStageImpl

        llm = AsyncMock()
        llm.generate.return_value = "Counter-argument: the methodology is flawed."

        stage = CounterArgumentStageImpl(llm)
        ctx = _make_ctx(
            query="Is AGI near?",
            contradictions=[
                {"analysis": "Some claim AGI is near."},
            ],
        )

        result = await stage.execute(ctx)

        assert llm.generate.call_count >= 1  # deep_read + optional verifier
        assert len(result.relations) == 1
        assert result.relations[0]["counter_argument"] == "Counter-argument: the methodology is flawed."

    @pytest.mark.asyncio
    async def test_falls_back_to_search_results_when_no_contradictions(self):
        """When no contradiction analysis, should use search results as findings."""
        from minerva.pipeline.stages import CounterArgumentStageImpl

        llm = AsyncMock()
        llm.generate.return_value = "Counter-arguments based on search."

        stage = CounterArgumentStageImpl(llm)
        ctx = _make_ctx(
            query="Test",
            contradictions=[],
            search_results=[
                _make_search_result(title="R1", snippet="Snippet one."),
                _make_search_result(title="R2", snippet="Snippet two."),
            ],
        )

        result = await stage.execute(ctx)

        assert llm.generate.call_count >= 1  # deep_read + optional verifier
        prompt_text = llm.generate.call_args[1]["prompt"]
        assert "R1" in prompt_text
        assert "Snippet one" in prompt_text

    @pytest.mark.asyncio
    async def test_handles_llm_exception_gracefully(self):
        """Should store fallback message when LLM fails."""
        from minerva.pipeline.stages import CounterArgumentStageImpl

        llm = AsyncMock()
        llm.generate.side_effect = RuntimeError("LLM down")

        stage = CounterArgumentStageImpl(llm)
        ctx = _make_ctx(
            query="Test",
            contradictions=[{"analysis": "Some analysis."}],
        )

        result = await stage.execute(ctx)

        assert result.relations[0]["counter_argument"] == "Counter-argument analysis unavailable."


# ===================================================================
# MultiModelVotingStageImpl
# ===================================================================

class TestMultiModelVotingStageImpl:
    """Tests for MultiModelVotingStageImpl — multi-model voting (L4)."""

    @pytest.mark.asyncio
    async def test_votes_on_conclusions(self):
        """Should aggregate relations and send to LLM for multi-model voting."""
        from minerva.pipeline.stages import MultiModelVotingStageImpl

        llm = AsyncMock()
        llm.generate.return_value = "Voting: AGREE on claim 1, DISAGREE on claim 2."

        stage = MultiModelVotingStageImpl(llm)
        ctx = _make_ctx(
            query="What is the future of AI?",
            relations=[
                {"reasoning": "Deep reasoning result."},
                {"counter_argument": "Alternative perspective."},
            ],
        )

        result = await stage.execute(ctx)

        assert llm.generate.call_count >= 1  # deep_read + optional verifier
        assert len(result.relations) == 3  # 2 original + 1 voting
        assert result.relations[-1]["voting"] == "Voting: AGREE on claim 1, DISAGREE on claim 2."

    @pytest.mark.asyncio
    async def test_returns_insufficient_data_when_no_relations(self):
        """Should store fallback message when no relation data is available."""
        from minerva.pipeline.stages import MultiModelVotingStageImpl

        llm = AsyncMock()
        stage = MultiModelVotingStageImpl(llm)
        ctx = _make_ctx(query="Test", relations=[])

        result = await stage.execute(ctx)

        llm.generate.assert_not_called()
        assert len(result.relations) == 1
        assert "Insufficient data" in result.relations[0]["voting"]

    @pytest.mark.asyncio
    async def test_handles_llm_exception_gracefully(self):
        """Should store fallback message when LLM fails."""
        from minerva.pipeline.stages import MultiModelVotingStageImpl

        llm = AsyncMock()
        llm.generate.side_effect = RuntimeError("LLM down")

        stage = MultiModelVotingStageImpl(llm)
        ctx = _make_ctx(
            query="Test",
            relations=[{"reasoning": "Some reasoning."}],
        )

        result = await stage.execute(ctx)

        assert result.relations[-1]["voting"] == "Multi-model voting unavailable."


# ===================================================================
# ExtendedOutputStageImpl (L4)
# ===================================================================

class TestExtendedOutputStageImpl:
    """Tests for ExtendedOutputStageImpl — L4 extended report."""

    @pytest.mark.asyncio
    async def test_writes_extended_report(self, tmp_path):
        """Should write an L4 extended report with all sections."""
        from minerva.pipeline.stages import ExtendedOutputStageImpl

        stage = ExtendedOutputStageImpl(
            llm_client=None,
            knowledge_store=None,
            report_dir=str(tmp_path),
        )
        ctx = _make_ctx(
            query="Extended Research",
            level=ResearchLevel.L4,
            search_results=[
                _make_search_result(
                    title="Key Paper",
                    url="http://example.com",
                    source="scholar",
                ),
                _make_search_result(
                    title="Supporting Study",
                    url="http://example.org",
                    source="web",
                ),
            ],
            entities=[{"id": "e1", "type": "Tech"}],
            contradictions=[{"analysis": "Deep cross-analysis text." * 10}],
            relations=[
                {"counter_argument": "Counter-argument analysis."},
                {"voting": "Multi-model voting results."},
            ],
            cost=2.50,
        )

        result = await stage.execute(ctx)

        assert result.report is not None
        assert "Extended Research Report" in result.report
        assert "Counter-Arguments" in result.report
        assert "Multi-Model Voting" in result.report
        assert "Cross-Analysis" in result.report
        assert "Full Citation List" in result.report
        assert "Counter-argument analysis." in result.report
        assert "Multi-model voting results." in result.report
        assert result.report_path.endswith("_L4.md")
        assert Path(result.report_path).exists()

    @pytest.mark.asyncio
    async def test_handles_missing_counter_argument_and_voting(self, tmp_path):
        """Should gracefully handle missing counter-argument and voting sections."""
        from minerva.pipeline.stages import ExtendedOutputStageImpl

        stage = ExtendedOutputStageImpl(
            llm_client=None,
            knowledge_store=None,
            report_dir=str(tmp_path),
        )
        ctx = _make_ctx(
            query="Basic L4",
            level=ResearchLevel.L4,
            search_results=[_make_search_result()],
            relations=[],
            contradictions=[],
            cost=0.0,
        )

        result = await stage.execute(ctx)

        assert "No counter-arguments generated." in result.report
        assert "Multi-model voting not performed." in result.report
        assert "No cross-analysis available." in result.report


# ===================================================================
# spacy_to_entity_type (module-level helper)
# ===================================================================

class TestSpacyToEntityType:
    """Tests for the spacy_to_entity_type mapping function."""

    def test_known_labels(self):
        """Should map known spaCy NER labels to Minerva ontology types."""
        from minerva.shared import spacy_to_entity_type

        assert spacy_to_entity_type("ORG") == "Organization"
        assert spacy_to_entity_type("PERSON") == "Person"
        assert spacy_to_entity_type("GPE") == "Organization"
        assert spacy_to_entity_type("PRODUCT") == "Product"
        assert spacy_to_entity_type("WORK_OF_ART") == "Publication"
        assert spacy_to_entity_type("DATE") == "Event"
        assert spacy_to_entity_type("EVENT") == "Event"

    def test_unknown_label_defaults_to_concept(self):
        """Unknown labels should map to 'Concept'."""
        from minerva.shared import spacy_to_entity_type

        assert spacy_to_entity_type("MONEY") == "Concept"
        assert spacy_to_entity_type("UNKNOWN_LABEL") == "Concept"
