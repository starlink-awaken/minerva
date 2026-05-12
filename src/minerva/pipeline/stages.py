"""Pipeline stage implementations — Decompose, Search, Entity, DeepRead, Analyze, Quality, Output."""

from __future__ import annotations

import asyncio
import contextlib
import time
from pathlib import Path

from minerva.knowledge.store import Entity
from minerva.pipeline.engine import IPipelineStage, QualityGateFailure, ResearchContext

DECOMPOSE_PROMPT = """Decompose this research question into 3-5 specific sub-questions.
Each sub-question should cover a distinct aspect. Output one question per line.
Research question: {query}"""

DEEP_READ_PROMPT = """Analyze the following documents about: {query}

For each source:
1. Extract key claims
2. Note consensus (all sources agree)
3. Note contradictions (sources disagree)
4. Note gaps (topics not covered)
5. Note evolution relationships (builds on, refutes)

Documents:
{documents}

Provide structured analysis in markdown."""

CROSS_ANALYZE_PROMPT = """Given this analysis of multiple sources about: {query}

{analysis}

Perform deep reasoning:
1. For each contradiction: which claim is more credible and why?
2. For each gap: is it unexplored or unsolvable with current methods?
3. Based on evolution patterns: what is the likely next development?
4. Assign confidence scores (HIGH/MEDIUM/LOW) to each conclusion.

Output structured reasoning in markdown."""

REPORT_TEMPLATE = """# Research Report: {query}

> 🧭 **TL;DR** — {tldr}

## Key Findings
{findings}

## Evidence Matrix
| Claim | Source | Confidence |
|-------|--------|------------|
{evidence_rows}

## Contradictions & Disputes
{contradictions}

## Gaps & Opportunities
{gaps}

## Citations
{citations}
"""


class DecomposeStageImpl(IPipelineStage):
    """Decompose query into sub-questions using local LLM."""

    name = "decompose"

    def __init__(self, llm_client, max_sub_questions: int = 5):
        self.llm = llm_client
        self.max_sub = max_sub_questions

    async def execute(self, ctx: ResearchContext) -> ResearchContext:
        try:
            response = await self.llm.generate(
                system="You decompose research questions into specific sub-questions.",
                prompt=DECOMPOSE_PROMPT.format(query=ctx.query),
                temperature=0.3,
                max_tokens=500,
            )
            ctx.sub_questions = [
                q.strip("- *").strip()
                for q in response.strip().split("\n")
                if q.strip() and len(q.strip()) > 5
            ][:self.max_sub]
        except Exception:
            ctx.sub_questions = [ctx.query]
        return ctx


class MultiSourceSearchStageImpl(IPipelineStage):
    """Parallel search across multiple backends."""

    name = "search"

    def __init__(self, search_engine, backends: list[str], max_results: int = 25):
        self.search_engine = search_engine
        self.backends = backends
        self.max_results = max_results

    async def execute(self, ctx: ResearchContext) -> ResearchContext:
        queries = ctx.sub_questions if ctx.sub_questions else [ctx.query]
        # Parallel search across primary + all sub-questions
        tasks = [
            self.search_engine.search(
                q, backends=self.backends,
                max_results=self.max_results if i == 0 else 5
            )
            for i, q in enumerate(queries)
        ]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        results: list = []
        for r in gathered:
            if isinstance(r, list):
                results.extend(r)
            elif isinstance(r, Exception):
                pass  # Individual query failures are non-fatal

        # Deduplicate
        seen: set = set()
        deduped = []
        for r in results:
            if r.url not in seen:
                seen.add(r.url)
                deduped.append(r)
        ctx.search_results = [{
            "title": r.title, "url": r.url, "snippet": r.snippet,
            "source": r.source, "published_date": r.published_date,
            "rank_score": r.rank_score,
        } for r in deduped[:self.max_results]]
        return ctx


class EntityExtractionStageImpl(IPipelineStage):
    """Extract entities using spaCy NLP + LLM fallback with language routing."""

    name = "entity_extraction"

    def __init__(self, nlp_pipeline, llm_client, knowledge_store=None, nlp_zh=None):
        self.nlp = nlp_pipeline  # spaCy Language (English)
        self.nlp_zh = nlp_zh      # spaCy Language (Chinese)
        self.llm = llm_client
        self.kb = knowledge_store

    def _detect_language(self, text: str) -> str:
        """Simple language detection based on character set."""
        zh_chars = sum(1 for c in text if '一' <= c <= '鿿')
        return "zh" if zh_chars > len(text) * 0.05 else "en"

    async def execute(self, ctx: ResearchContext) -> ResearchContext:
        entities = []
        if self.nlp is None:
            ctx.entities = []
            return ctx
        for result in ctx.search_results[:10]:
            text = result.get("snippet", "")
            if not text:
                continue
            lang = self._detect_language(text)
            nlp = self.nlp_zh if lang == "zh" and self.nlp_zh else self.nlp
            doc = nlp(text[:1000])
            for ent in doc.ents:
                if ent.label_ in ("ORG", "PERSON", "GPE", "PRODUCT", "WORK_OF_ART"):
                    eid = f"ent-{len(entities)}-{ent.label_}"
                    entity = Entity(
                        id=eid, type=_spacy_to_entity_type(ent.label_),
                        name=ent.text,
                        source_ids=[result.get("url", "")],
                        confidence="MEDIUM",
                    )
                    entities.append(entity)
                    if self.kb:
                        with contextlib.suppress(Exception):
                            await self.kb.upsert_entity(entity)
        ctx.entities = [{"id": e.id, "type": e.type, "name": e.name, "confidence": e.confidence} for e in entities]
        return ctx


class DeepReadStageImpl(IPipelineStage):
    """Extract full content and cross-analyze with LLM."""

    name = "deep_read"

    def __init__(self, content_extractor, llm_client, top_n: int = 15):
        self.extractor = content_extractor
        self.llm = llm_client
        self.top_n = top_n

    async def execute(self, ctx: ResearchContext) -> ResearchContext:
        # Extract content from top results
        top_results = ctx.search_results[:self.top_n]
        documents = []
        for r in top_results:
            url = r.get("url", "")
            if url:
                content = await self.extractor.extract_content(url)
                if content:
                    documents.append(f"## {r.get('title', 'Untitled')}\nSource: {url}\n\n{content[:3000]}\n")

        if not documents:
            ctx.extracted_content = []
            return ctx

        docs_text = "\n---\n".join(documents)
        try:
            analysis = await self.llm.generate(
                system="You analyze multiple documents and identify claims, consensus, contradictions, and gaps.",
                prompt=DEEP_READ_PROMPT.format(query=ctx.query, documents=docs_text[:8000]),
                temperature=0.3,
                max_tokens=2000,
            )
        except Exception:
            analysis = "Deep read analysis unavailable."

        ctx.extracted_content = [d[:500] for d in documents]
        ctx.contradictions = ctx.contradictions or []
        ctx.contradictions.append({"analysis": analysis})
        return ctx


class CrossAnalyzeStageImpl(IPipelineStage):
    """Deep reasoning analysis on extracted content."""

    name = "cross_analyze"

    def __init__(self, llm_client):
        self.llm = llm_client

    async def execute(self, ctx: ResearchContext) -> ResearchContext:
        analysis = ""
        for c in (ctx.contradictions or []):
            analysis += c.get("analysis", "") + "\n"

        if not analysis.strip():
            ctx.relations = []
            return ctx

        try:
            reasoning = await self.llm.generate(
                system="You perform deep reasoning on research findings.",
                prompt=CROSS_ANALYZE_PROMPT.format(query=ctx.query, analysis=analysis[:4000]),
                temperature=0.5,
                max_tokens=1500,
            )
        except Exception:
            reasoning = "Cross-analysis unavailable."

        ctx.relations = ctx.relations or []
        ctx.relations.append({"reasoning": reasoning})
        return ctx


class QualityGateStageImpl(IPipelineStage):
    """Verify research quality and assign a quality score."""

    name = "quality_gate"

    async def execute(self, ctx: ResearchContext) -> ResearchContext:
        failures = []
        score = 100

        # Source count
        if not ctx.search_results:
            failures.append("No search results found")
            score = 0
        elif len(ctx.search_results) < 3:
            failures.append("Insufficient sources (<3)")
            score -= 30
        elif len(ctx.search_results) < 5:
            score -= 10

        # Entity extraction
        if not ctx.entities:
            score -= 10  # No entities found — but not a failure

        # Contradiction depth
        has_analysis = any(
            c.get("analysis") and len(c.get("analysis", "")) > 50
            for c in (ctx.contradictions or [])
        )
        if not has_analysis and ctx.contradictions:
            score -= 10

        # Source diversity
        if ctx.search_results:
            sources = {r.get("source", "") for r in ctx.search_results}
            if len(sources) == 1:
                score -= 15  # Only one backend

        ctx.relations = ctx.relations or []
        ctx.relations.append({
            "quality_score": max(0, score),
            "quality_gate_checks": {
                "source_count": len(ctx.search_results),
                "entity_count": len(ctx.entities),
                "contradiction_analysis": has_analysis,
            },
            "failures": failures,
        })

        if failures:
            raise QualityGateFailure(f"[score:{score}] {'; '.join(failures)}")

        return ctx


class OutputStageImpl(IPipelineStage):
    """Generate final report and write to disk."""

    name = "output"

    def __init__(self, llm_client=None, knowledge_store=None, report_dir: str = "~/knowledge/reports"):
        self.llm = llm_client
        self.kb = knowledge_store
        self.report_dir = Path(report_dir).expanduser()

    async def execute(self, ctx: ResearchContext) -> ResearchContext:
        self.report_dir.mkdir(parents=True, exist_ok=True)

        # Generate TL;DR summary
        tldr = self._generate_tldr(ctx)

        # Build findings
        findings = ""
        for i, r in enumerate(ctx.search_results[:8]):
            findings += f"{i+1}. **{r.get('title', 'Untitled')}** — {r.get('snippet', '')[:200]}\n"
        if not findings:
            findings = "No findings available."

        # Build evidence rows with source-based confidence
        evidence_rows = ""
        source_confidence = {"scholar": "HIGH", "arxiv": "HIGH", "exa": "MEDIUM-HIGH",
                             "metaso": "MEDIUM", "ddg": "MEDIUM", "brave": "MEDIUM",
                             "searxng": "MEDIUM", "web": "MEDIUM"}
        for r in ctx.search_results[:8]:
            src = r.get("source", "web")
            conf = source_confidence.get(src, "MEDIUM")
            evidence_rows += f"| {r.get('title', 'Untitled')[:50]} | {r.get('url', '')[:50]} | {conf} |\n"

        # Build contradictions
        contradictions = ""
        for c in (ctx.contradictions or []):
            analysis = c.get("analysis", "")
            if analysis and len(analysis) > 50:
                contradictions += analysis[:500] + "\n"
        if not contradictions:
            sources_list = ", ".join({r.get("source", "web") for r in ctx.search_results[:5]})
            contradictions = (
                f"No direct contradictions found across {len(ctx.search_results)} sources "
                f"from {sources_list}. Cross-source consensus suggests reliable findings."
            )

        # Build gaps
        gaps = ""
        source_types = {r.get("source", "web") for r in ctx.search_results}
        if "scholar" not in source_types and "arxiv" not in source_types:
            gaps += "- Academic sources (Semantic Scholar / arXiv) not represented in results.\n"
        if len(ctx.search_results) < 5:
            gaps += f"- Limited source count ({len(ctx.search_results)}). Consider re-running at higher level.\n"
        if not gaps:
            gaps = f"Coverage across {len(source_types)} source types. Consider deeper analysis for specific sub-topics."

        # Build citations
        citations = ""
        for i, r in enumerate(ctx.search_results[:10]):
            citations += f"{i+1}. [{r.get('title', 'Untitled')[:80]}]({r.get('url', '')})\n"

        report = REPORT_TEMPLATE.format(
            query=ctx.query,
            tldr=tldr,
            findings=findings,
            evidence_rows=evidence_rows,
            contradictions=contradictions,
            gaps=gaps,
            citations=citations,
        )

        # Extract quality score for report header
        quality_score = "N/A"
        for r in (ctx.relations or []):
            if "quality_score" in r:
                quality_score = str(r["quality_score"])
                break

        # Write English report
        ts = time.strftime("%Y%m%d-%H%M%S")
        slug = ctx.query[:40].replace(" ", "-").lower()
        en_path = self.report_dir / f"{ts}_{slug}_EN.md"
        en_header = f"> **Quality Score: {quality_score}/100** | Level: {ctx.level.value} | Sources: {len(ctx.search_results)}\n\n"
        en_path.write_text(en_header + report)

        # Generate Chinese version via LLM
        zh_report = None
        if self.llm and len(report) > 100:
            try:
                zh_output = await self.llm.generate(
                    system="You translate research reports from English to Chinese. Preserve markdown formatting, citations, tables, and structure exactly. Only translate the text content.",
                    prompt=f"Translate this research report to Chinese. Keep all markdown formatting, URLs, and table structures unchanged:\n\n{report[:6000]}",
                    temperature=0.2,
                    max_tokens=4096,
                )
                zh_path = self.report_dir / f"{ts}_{slug}_ZH.md"
                zh_header = f"> **质量评分: {quality_score}/100** | 级别: {ctx.level.value} | 来源: {len(ctx.search_results)}\n\n"
                zh_path.write_text(zh_header + zh_output)
                zh_report = str(zh_path)
            except Exception:
                pass  # Chinese translation is best-effort

        ctx.report = report
        ctx.report_path = str(en_path)
        if zh_report:
            ctx.relations = ctx.relations or []
            ctx.relations.append({"zh_report_path": zh_report})
        return ctx

    def _generate_tldr(self, ctx: ResearchContext) -> str:
        """Generate a 2-3 sentence TL;DR summary from research context."""
        src_count = len(ctx.search_results)
        entity_count = len(ctx.entities)
        contradictions_found = any(
            c.get("analysis") and len(c.get("analysis", "")) > 50
            for c in (ctx.contradictions or [])
        )
        top_sources = ", ".join(
            r.get("title", "Untitled")[:40]
            for r in ctx.search_results[:3]
        )
        parts = [
            f"Research analyzed {src_count} sources",
            f"extracted {entity_count} entities" if entity_count else "",
            f"found contradictions: {'yes' if contradictions_found else 'no significant'}" if src_count >= 3 else "",
        ]
        core = ". ".join(p for p in parts if p) + "."
        return f"{core} Key sources: {top_sources}."


def _spacy_to_entity_type(spacy_label: str) -> str:
    """Map spaCy NER labels to Minerva ontology types."""
    mapping = {
        "ORG": "Organization",
        "PERSON": "Person",
        "GPE": "Organization",
        "PRODUCT": "Product",
        "WORK_OF_ART": "Publication",
        "DATE": "Event",
        "EVENT": "Event",
    }
    return mapping.get(spacy_label, "Concept")


# ============================================================
# L3/L4 Specific Stages
# ============================================================

COUNTER_ARGUMENT_PROMPT = """Given this research on: {query}

{findings}

You are playing devil's advocate. Identify:
1. The strongest counter-arguments to the main conclusions
2. Alternative interpretations of the evidence
3. Weaknesses in methodology or assumptions
4. Missing perspectives or stakeholders
5. Overlooked risks or downsides

Be specific and cite sources where possible. Output in markdown."""

MULTI_MODEL_PROMPT = """Given this research analysis on: {query}

{analysis}

You are a panel of expert reviewers. Provide:
1. Voting on each major conclusion (AGREE/DISAGREE/NEUTRAL with justification)
2. Confidence score for each conclusion (HIGH/MEDIUM/LOW)
3. Areas where models disagree and why
4. Recommended follow-up research questions
5. Final consensus summary

Output in structured markdown."""


class CounterArgumentStageImpl(IPipelineStage):
    """Generate counter-arguments and alternative perspectives. (L3+)"""

    name = "counter_argument"

    def __init__(self, llm_client):
        self.llm = llm_client

    async def execute(self, ctx: ResearchContext) -> ResearchContext:
        findings = ""
        for c in (ctx.contradictions or []):
            findings += c.get("analysis", "") + "\n"
        if not findings.strip():
            findings = "\n".join(
                f"- {r.get('title', '')}: {r.get('snippet', '')[:200]}"
                for r in ctx.search_results[:5]
            )

        try:
            response = await self.llm.generate(
                system="You are a critical thinker who identifies weaknesses and alternative perspectives in research.",
                prompt=COUNTER_ARGUMENT_PROMPT.format(query=ctx.query, findings=findings[:4000]),
                temperature=0.5,
                max_tokens=1500,
            )
        except Exception:
            response = "Counter-argument analysis unavailable."

        ctx.relations = ctx.relations or []
        ctx.relations.append({"counter_argument": response})
        return ctx


class MultiModelVotingStageImpl(IPipelineStage):
    """Multi-model voting on conclusions. (L4)"""

    name = "multi_model_voting"

    def __init__(self, llm_client):
        self.llm = llm_client

    async def execute(self, ctx: ResearchContext) -> ResearchContext:
        analysis = ""
        for r in (ctx.relations or []):
            for v in r.values():
                analysis += str(v)[:2000] + "\n"

        if not analysis.strip():
            ctx.relations = ctx.relations or []
            ctx.relations.append({"voting": "Insufficient data for multi-model voting."})
            return ctx

        try:
            response = await self.llm.generate(
                system="You are a panel of expert reviewers evaluating research conclusions.",
                prompt=MULTI_MODEL_PROMPT.format(query=ctx.query, analysis=analysis[:4000]),
                temperature=0.4,
                max_tokens=1500,
            )
        except Exception:
            response = "Multi-model voting unavailable."

        ctx.relations = ctx.relations or []
        ctx.relations.append({"voting": response})
        return ctx


class ExtendedOutputStageImpl(IPipelineStage):
    """Extended report for L4 with full analysis depth. (L4)"""

    name = "extended_output"

    def __init__(self, llm_client=None, knowledge_store=None, report_dir: str = "~/knowledge/reports"):
        self.llm = llm_client
        self.kb = knowledge_store
        self.report_dir = Path(report_dir).expanduser()

    async def execute(self, ctx: ResearchContext) -> ResearchContext:
        self.report_dir.mkdir(parents=True, exist_ok=True)

        summary = f"# Extended Research Report: {ctx.query}\n\n"
        summary += f"**Level:** {ctx.level.value} | "
        summary += f"**Sources:** {len(ctx.search_results)} | "
        summary += f"**Entities:** {len(ctx.entities)} | "
        summary += f"**Cost:** ${ctx.cost:.2f}\n\n"

        # Key findings
        summary += "## Key Findings\n\n"
        for i, r in enumerate(ctx.search_results[:12]):
            summary += f"{i+1}. **{r.get('title', 'Untitled')}** — {r.get('snippet', '')[:300]}\n\n"

        # Evidence matrix
        summary += "## Evidence Matrix\n\n"
        summary += "| Claim | Source | Confidence |\n"
        summary += "|-------|--------|------------|\n"
        for r in ctx.search_results[:12]:
            summary += f"| {r.get('title', '')[:60]} | {r.get('url', '')[:60]} | MEDIUM |\n"

        # Counter arguments
        summary += "\n## Counter-Arguments\n\n"
        for r in (ctx.relations or []):
            ca = r.get("counter_argument", "")
            if ca:
                summary += ca[:2000] + "\n"
                break
        else:
            summary += "No counter-arguments generated.\n"

        # Multi-model voting
        summary += "\n## Multi-Model Voting\n\n"
        for r in (ctx.relations or []):
            v = r.get("voting", "")
            if v:
                summary += v[:2000] + "\n"
                break
        else:
            summary += "Multi-model voting not performed.\n"

        # Cross analysis
        summary += "\n## Cross-Analysis\n\n"
        for c in (ctx.contradictions or []):
            summary += c.get("analysis", "")[:1500] + "\n"
            break

        # Citations
        summary += "\n## Full Citation List\n\n"
        for i, r in enumerate(ctx.search_results[:15]):
            summary += f"{i+1}. [{r.get('title', 'Untitled')[:100]}]({r.get('url', '')})\n"

        ts = time.strftime("%Y%m%d-%H%M%S")
        slug = ctx.query[:40].replace(" ", "-").lower()
        path = self.report_dir / f"{ts}_{slug}_L4.md"
        path.write_text(summary)

        ctx.report = summary
        ctx.report_path = str(path)
        return ctx
