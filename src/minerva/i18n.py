"""
Minerva i18n — Multilingual support for research outputs and UI.

Supports: English (en), Chinese (zh), Japanese (ja), Korean (ko).
"""

from __future__ import annotations

# --- Language detection ---

_DEFAULT_LANG = "en"
_SUPPORTED = {"en", "zh", "ja", "ko"}


def detect_language(text: str) -> str:
    """Detect language from text content.

    Simple CJK detection heuristic:
    - If >10% CJK Unified Ideographs → zh/ja/ko
    - Check Hiragana/Katakana → ja
    - Check Hangul → ko
    - Default → zh (simplified Chinese)
    """
    if not text:
        return _DEFAULT_LANG

    total = len(text)
    cjk = sum(1 for c in text if '一' <= c <= '鿿')
    hiragana = sum(1 for c in text if '぀' <= c <= 'ゟ')
    katakana = sum(1 for c in text if '゠' <= c <= 'ヿ')
    hangul = sum(1 for c in text if '가' <= c <= '힯')

    cjk_ratio = cjk / total if total > 0 else 0

    if cjk_ratio > 0.1:
        if hiragana + katakana > cjk * 0.3:
            return "ja"
        if hangul > cjk * 0.3:
            return "ko"
        return "zh"

    return _DEFAULT_LANG


# --- Translation strings ---

STRINGS = {
    "en": {
        "research.complete": "Research complete",
        "research.failed": "Research failed",
        "research.cost_warning": "Estimated cost: ${cost:.2f}",
        "research.privacy_warning": "PRIVACY: Cloud APIs disabled due to data sensitivity",
        "pipeline.stage.decompose": "Decomposing query into sub-questions",
        "pipeline.stage.search": "Searching across {backends}",
        "pipeline.stage.entity": "Extracting entities",
        "pipeline.stage.deep_read": "Deep reading top {n} sources",
        "pipeline.stage.analyze": "Cross-analyzing findings",
        "pipeline.stage.quality": "Quality gate check",
        "pipeline.stage.output": "Generating research report",
        "report.section.summary": "Executive Summary",
        "report.section.findings": "Key Findings",
        "report.section.evidence": "Evidence Matrix",
        "report.section.contradictions": "Contradictions & Disputes",
        "report.section.timeline": "Evolution Timeline",
        "report.section.gaps": "Gaps & Opportunities",
        "report.section.citations": "Citations",
        "report.confidence.high": "HIGH",
        "report.confidence.medium": "MEDIUM",
        "report.confidence.low": "LOW",
        "triage.dimension.domain": "Domain Complexity",
        "triage.dimension.time": "Timeliness",
        "triage.dimension.depth": "Analysis Depth",
        "triage.dimension.source": "Multi-Source Needs",
        "triage.dimension.privacy": "Privacy Sensitivity",
        "error.budget_exceeded": "Budget exceeded: ${cost:.2f} > ${budget:.2f} remaining",
        "error.llm_unavailable": "LLM service unavailable, using rule-based fallback",
        "error.search_failed": "Search backend {backend} failed: {error}",
        "error.quality_gate": "Quality gate failed: {reason}",
    },
    "zh": {
        "research.complete": "研究完成",
        "research.failed": "研究失败",
        "research.cost_warning": "预估成本：${cost:.2f}",
        "research.privacy_warning": "隐私保护：因数据敏感，已禁用云端API",
        "pipeline.stage.decompose": "正在将问题分解为子问题",
        "pipeline.stage.search": "正在从 {backends} 搜索",
        "pipeline.stage.entity": "正在提取实体",
        "pipeline.stage.deep_read": "正在深度阅读前 {n} 个来源",
        "pipeline.stage.analyze": "正在交叉分析发现",
        "pipeline.stage.quality": "质量把关检查",
        "pipeline.stage.output": "正在生成研究报告",
        "report.section.summary": "执行摘要",
        "report.section.findings": "关键发现",
        "report.section.evidence": "证据矩阵",
        "report.section.contradictions": "矛盾与争议",
        "report.section.timeline": "演进时间线",
        "report.section.gaps": "空白与机会",
        "report.section.citations": "引用来源",
        "report.confidence.high": "高",
        "report.confidence.medium": "中",
        "report.confidence.low": "低",
        "triage.dimension.domain": "领域复杂度",
        "triage.dimension.time": "时效性",
        "triage.dimension.depth": "分析深度",
        "triage.dimension.source": "多源需求",
        "triage.dimension.privacy": "隐私敏感度",
        "error.budget_exceeded": "超出预算：${cost:.2f} > 剩余 ${budget:.2f}",
        "error.llm_unavailable": "LLM服务不可用，使用规则回退",
        "error.search_failed": "搜索引擎 {backend} 失败：{error}",
        "error.quality_gate": "质量检查未通过：{reason}",
    },
    "ja": {
        "research.complete": "調査完了",
        "research.failed": "調査失敗",
        "report.section.summary": "要約",
        "report.section.findings": "主な発見",
        "report.section.citations": "引用元",
        "report.confidence.high": "高",
        "report.confidence.medium": "中",
        "report.confidence.low": "低",
    },
    "ko": {
        "research.complete": "연구 완료",
        "research.failed": "연구 실패",
        "report.section.summary": "요약",
        "report.section.findings": "주요 발견",
        "report.section.citations": "인용 출처",
        "report.confidence.high": "높음",
        "report.confidence.medium": "중간",
        "report.confidence.low": "낮음",
    },
}


def get_string(key: str, lang: str = "en", **kwargs) -> str:
    """Get localized string, falling back to English if translation missing.

    Args:
        key: String key (e.g., 'research.complete')
        lang: Language code (en/zh/ja/ko)
        **kwargs: Format variables

    Returns:
        Localized and formatted string
    """
    lang_strs = STRINGS.get(lang, STRINGS["en"])
    text = lang_strs.get(key)
    if text is None:
        # Fallback: try English
        text = STRINGS["en"].get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text


def get_report_template(lang: str) -> str:
    """Get research report template in the specified language."""
    def t(k, **kw):
        return get_string(k, lang, **kw)

    return f"""# {t('report.section.summary')}

[200-300 word executive summary]

---

## {t('report.section.findings')}

### Finding 1: [Title]
- {t('report.confidence.high')} / {t('report.confidence.medium')} / {t('report.confidence.low')}
- Sources: [links]
- Analysis: [detailed analysis]

### Finding 2: [Title]
...

---

## {t('report.section.evidence')}

| Claim | Source | Confidence | Contradictions |
|-------|--------|------------|----------------|
| ... | ... | ... | ... |

---

## {t('report.section.contradictions')}

### Contradiction 1: [Topic]
- Position A: [source] claims ...
- Position B: [source] claims ...
- Resolution: [analysis]

---

## {t('report.section.timeline')}

```mermaid
timeline
    [Event timeline]
```

---

## {t('report.section.gaps')}

- Gap 1: [topic] — no source discusses [aspect]
- Gap 2: ...

---

## {t('report.section.citations')}

1. [Author]. [Title]. [Venue], [Date]. [URL]
2. ...
"""
