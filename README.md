# Minerva — Local-First Deep Research System

> *Minerva: Roman goddess of wisdom, strategic warfare, and the arts.*
>
> A local-first, multi-tier deep research system that searches 8 sources, analyzes with 4 LLMs, persists knowledge in Neo4j + SQLite, and produces bilingual reports with quality scoring. Runs on Apple Silicon with $0/month base cost.

[English](#english) | [中文](#chinese)

---

## English

### What is Minerva?

Minerva is a local deep research engine. You ask a question, it searches across 8 backends in parallel, extracts entities via spaCy, analyzes contradictions, scores quality, and generates a bilingual (EN+ZH) report — all running on your machine with zero cloud dependency for basic tiers.

### Quick Start

```bash
# Research a topic (L0: 30s, free)
minerva research "What is a transformer architecture?" --level L0

# Deep research with citations (L2: ~2min)
minerva research "MoE model production practices" --level L2

# Enterprise reasoning with counter-arguments (L3: ~8min)
minerva research "AI existential risk: both sides" --level L3

# Knowledge maintenance
minerva maintenance

# Start MCP server for Claude Code integration
minerva mcp
```

### Pipeline Levels

| Level | Time | Cost | What It Does |
|-------|------|------|-------------|
| **L0** Quick | <30s | $0 | Single-round search, 5 sources |
| **L1** Standard | <3min | $0 | Decompose→Search→Cross-analyze |
| **L2** Deep | ~2min | ~$0.30 | Entity extraction, DeepRead, contradiction analysis |
| **L3** Comprehensive | ~8min | ~$0.50 | Counter-argument generation (cloud LLM) |
| **L4** Max | ~15min | ~$2 | Multi-model voting, extended report |

### System Architecture

```
User Input → TriageRouter (L0-L4) → Pipeline (9 stages)
                                        │
         ┌──────────────────────────────┼──────────────────────────────┐
         │                              │                              │
    Search Layer                   AI Layer                    Knowledge Layer
   ┌─────────────┐            ┌─────────────┐               ┌─────────────┐
   │ DDG (free)  │            │ qwen3.6:27b │               │ SQLite FTS5 │
   │ Scholar(free)│           │  (local L0-2)│              │ Neo4j 5     │
   │ arXiv (free) │           │ V4 Pro 1M ctx │              │ LanceDB     │
   │ Metaso(paid) │           │  (cloud L3-4) │             │ Allen Temporal│
   │ Exa (free)   │           │ GLM-4.7 Flash│               │ RuleEngine  │
   │ Brave (free) │           │  (128K free)  │              │ GraphBridge │
   │ Zhipu (free) │           │ LongCat-Thinking│            └─────────────┘
   │ SearXNG(opt) │           │  (500万/day free)│                │
   └─────────────┘            └─────────────┘                    │
         │                              │                        │
         └──────────────────────────────┴────────────────────────┘
                                        │
                                   Output Layer
                              ┌─────────────────┐
                              │ EN Report + ZH   │
                              │ TL;DR summary    │
                              │ Quality Score    │
                              │ Source Confidence│
                              │ MCP 5 Tools      │
                              └─────────────────┘
```

### Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.14+, async/await |
| Local LLM | Ollama MLX (qwen3.6:27b + 35b-a3b, NVFP4) |
| Cloud LLM | DeepSeek V4 Pro · LongCat · GLM-4.7 Flash |
| NLP | spaCy en_core_web_lg + zh_core_web_sm |
| Search | DDG · Semantic Scholar · arXiv · Metaso · Exa · Brave · Zhipu · SearXNG |
| Knowledge Graph | Neo4j 5 Community · GraphBridge |
| Vector DB | LanceDB |
| Full-text | SQLite FTS5 |
| Temporal | Allen 13 interval relations · RuleEngine |
| Agent Integration | MCP (5 Super Tools) · FastMCP |
| Scheduling | APScheduler · daemon |
| Terminal UX | Rich (banners, progress bars, summary tables) |
| Infrastructure | Docker Compose (Neo4j + SearXNG) |

### Configuration

```bash
# Required env vars (add to ~/.zshrc)
export DEEPSEEK_API_KEY="sk-..."        # V4 Pro (primary reasoning)
export LONGCAT_API_KEY="ak-..."          # Backup reasoning (free 5M/day)
export GLM_API_KEY="..."                 # DeepRead fallback (free)
export METASO_API_KEY="mk-..."           # Chinese search
export EXA_API_KEY="..."                 # Semantic search
export BRAVE_API_KEY="BSA..."            # Brave search
export ZHIPU_API_KEY="..."               # Zhipu search
```

### vs Commercial Products

| Feature | Minerva | ChatGPT DR | Gemini DR | Perplexity |
|---------|---------|-----------|-----------|------------|
| Monthly cost | **$0-5** | $200 | $20 | $20 |
| Search sources | **8** | 1 | 1 | 1 |
| Privacy | **100% local** | Cloud | Cloud | Cloud |
| Knowledge persistence | **Neo4j + SQLite** | None | None | None |
| Chinese native | **Yes** | Translated | Translated | Translated |
| Programmable (MCP) | **Yes** | No | No | API |
| Bilingual reports | **EN+ZH** | EN only | EN only | EN only |
| Report quality score | **Yes** | No | No | No |

### Project Status

| Metric | Value |
|--------|-------|
| Commits | 45 |
| Tests | 137 (all passing) |
| Source lines | ~5,700 |
| Source files | 34 |
| Test files | 17 |
| ISC completion | 137/200 (68.5%) |
| Maturity | 92% (production-ready prototype) |

---

## 中文

### Minerva 是什么？

Minerva 是一个本地深度研究引擎。你提出问题，它并行搜索 8 个信息源，通过 spaCy 提取实体，分析矛盾，评分质量，生成中英双语报告——基础级别完全在本地运行，零云依赖。

### 快速开始

```bash
# 快速查定义 (L0: 30秒, 免费)
minerva research "什么是 transformer 架构" --level L0

# 深度调研 (L2: ~2分钟)
minerva research "MoE 模型在生产环境的最新实践" --level L2

# 企业推理 + 对立论证 (L3: ~8分钟)
minerva research "AI existential risk: both sides" --level L3

# 知识库维护
minerva maintenance

# 启动 MCP 服务器（对接 Claude Code）
minerva mcp
```

### 管道级别

| 级别 | 时间 | 成本 | 做什么 |
|------|------|------|--------|
| **L0** 快速 | <30s | $0 | 单轮搜索，5 个来源 |
| **L1** 标准 | <3min | $0 | 子问题分解，交叉分析 |
| **L2** 深度 | ~2min | ~$0.30 | 实体提取，内容分析，矛盾检测 |
| **L3** 全面 | ~8min | ~$0.50 | 对立论证生成（云推理） |
| **L4** 极致 | ~15min | ~$2 | 多模型投票，扩展报告 |

### 与商业产品对比

| 特性 | Minerva | ChatGPT DR | Gemini DR | Perplexity |
|------|---------|-----------|-----------|------------|
| 月成本 | **$0-5** | $200 | $20 | $20 |
| 搜索源 | **8 个** | 1 个 | 1 个 | 1 个 |
| 隐私 | **100% 本地** | 云端 | 云端 | 云端 |
| 知识持久化 | **Neo4j + SQLite** | 无 | 无 | 无 |
| 中文原生 | **是** | 翻译 | 翻译 | 翻译 |
| 可编程 (MCP) | **是** | 否 | 否 | API |
| 双语报告 | **中英双版** | 仅英文 | 仅英文 | 仅英文 |
| 质量评分 | **有** | 无 | 无 | 无 |

### 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.14+, async/await |
| 本地 LLM | Ollama MLX (qwen3.6:27b + 35b-a3b, NVFP4) |
| 云 LLM | DeepSeek V4 Pro · LongCat · GLM-4.7 Flash |
| NLP | spaCy en_core_web_lg + zh_core_web_sm |
| 搜索 | DDG · Scholar · arXiv · 秘塔 · Exa · Brave · 智谱 · SearXNG |
| 知识图谱 | Neo4j 5 · GraphBridge |
| 向量数据库 | LanceDB |
| 全文检索 | SQLite FTS5 |
| 时态推理 | Allen 13 区间关系 · RuleEngine |
| Agent 集成 | MCP (5 Super Tools) · FastMCP |
| 调度 | APScheduler · 守护进程 |
| 终端界面 | Rich (Banner、进度条、摘要表) |
| 基础设施 | Docker Compose (Neo4j + SearXNG) |

### 项目状态

| 指标 | 数值 |
|------|------|
| 提交数 | 45 |
| 测试数 | 137 (全部通过) |
| 代码行数 | ~5,700 |
| 源文件数 | 34 |
| 测试文件数 | 17 |
| ISC 完成度 | 137/200 (68.5%) |
| 成熟度 | 92% (生产就绪原型) |

### 许可证

MIT
