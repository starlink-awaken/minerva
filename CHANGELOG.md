# Changelog

## [0.11.0] — 2026-05-15

### Added
- Docker Compose全家桶: minerva + sophia + agora + neo4j + searxng 一键启动
- Dockerfile: Python 3.12-slim 镜像, Docker Hub 就绪
- D3.js 力导向图嵌入仪表盘: 知识图谱可视化
- `/api/graph` 端点: Neo4j 节点/边数据接口
- `minerva check` 命令: 6 项实时健康探测 (Ollama/SearXNG/Neo4j/API Key/依赖/存储)
- `scripts/demo.sh`: 8 步端到端验证脚本
- 审计日志系统: JSONL 结构化日志 (MCP/Web API/认证/限流)
- 13 项 Web API 集成测试: 路径遍历/输入验证/安全头/端点结构
- CI: pip-audit 依赖漏洞扫描 + mypy 类型检查
- DDG 搜索后端 (duckduckgo-search)

### Changed
- Templates 移入 `src/minerva/templates/` 支持 PyPI wheel 打包
- HTML 转义统一为 `html.escape` (消除 3 种 hand-rolled 实现)
- 范式分析提取为 `_build_paradigm_info()` 共享函数 (消除 2 处重复)
- `minerva init` 密码示例 `minerva123` → `generate-a-random-password-here`

### Fixed
- Semantic Scholar 429 限流: 指数退避 8s→16s→32s + 域间隔控制 + Retry-After
- L1 Quality Score N/A: 添加 QualityGateStageImpl
- Entity Extraction 始终 0: title+snippet 合并输入, 15 条结果
- CrossAnalyze <1ms: 增加 extracted_content 替代分析源
- arXiv HTTP 301: HTTPS 升级
- `paradigm_name` KeyError: 改用 .get() 安全查找
- Rich traceback 噪音: 移除 caught exception 的 exc_info
- Scholar null 条目: 添加 None 守卫
- GraphDataAccessor 驱动泄漏: 添加 close() + atexit 清理
- 审计日志导入时副作用: 延迟目录创建
- `_domain_last_call` 无界增长: LRU 50 条目淘汰
- ruff F841/F541: 零 lint

## [0.10.0] — 2026-05-14

### Added
- Enterprise governance: LICENSE, SECURITY.md, CHANGELOG.md, .env.example
- CI/CD pipeline (.github/workflows/ci.yml)
- SSE endpoint `/api/stream` for real-time status
- OpenAPI docs at `/docs` (Swagger UI)
- PDF report export (`/api/report/pdf`) with A4 print styles
- API key authentication middleware (`MINERVA_API_KEY`)
- `minerva init` first-time setup wizard
- L0-L4 E2E pipeline tests (6 tests)
- LanceDB `list_tables()` migration (deprecation fix)

### Changed
- L0 pipeline speed: 163s → 30s (5.4x faster)
- MCP server now auto-initializes executor (no manual init needed)
- DegradedExecutor extracted to module level
- OutputStage `execute()` skips ZH translation for L0
- Search backends: 429 retry logic added, bare excepts logged

### Fixed
- Quality score N/A → L0 now includes QualityGate
- MCP server executor initialization (was breaking 7/9 tools)
- Semantic scholar 429 rate limit auto-retry (2s backoff)
- LanceDB `table_names()` deprecation → `list_tables()`
- Sophia integration (paradigm info in API responses)
- Report rendering: TL;DR extraction, pipeline timeline, stats display

## [0.9.0] — 2026-05-13

### Added
- Sophia paradigm engine integration
- Web dashboard redesign (sidebar + dark theme)
- Pipeline stage timeline visualization
- Report markdown→HTML rendering (`/api/report`)
- Agora service convergence hub (separate project)

## [0.8.0] — 2026-05-12

### Added
- Circuit breaker for LLM providers
- SQLite startup integrity check + auto-repair
- HTTP connection pooling for search backends
- RAG context builder (LanceDB + SQLite hybrid)
- Embedding LRU cache
- Pipeline stage timeout + retry
- MinerU opt-in
- FastAPI web skeleton
- Research templates ×3

## [0.7.0] — 2026-05-12

### Added
- StepVerifier + GlobalVerifier (MiroThinker-inspired)
- Sliding window context management (top-5 full, rest summary)
- Process monitoring (Rich progress bars + log panel)
- TUI planning document

## [0.6.0] — 2026-05-11

### Added
- LanceDB vector store implementation
- Pipeline stage unit tests (56 tests)
- NotebookLM audio integration
- Graphify code graph sync
- SourceChecker GitHub trending

## [0.5.0] — Initial Release

- 8 search backends with RRF fusion
- L0-L4 5-tier pipeline
- SQLite + Neo4j + LanceDB knowledge base
- MCP server with 5 Super Tools
- Bilingual report output (EN+ZH)
- Cost guard with monthly budget
