# Changelog

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
