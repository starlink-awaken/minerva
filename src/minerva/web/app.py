"""FastAPI web application — health checks, research API, dashboard."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse

_executor_ref: dict = {}  # Holds executor singleton for API use


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init executor. Shutdown: cleanup."""
    try:
        from minerva.config import MinervaConfig
        from minerva.executor.executor import CostGuard, ResearchExecutor
        from minerva.knowledge.store import SQLiteKnowledgeStore
        from minerva.llm.client import OpenAICompatibleClient
        from minerva.pipeline.engine import create_default_pipeline
        from minerva.search.engine import SearchEngine
        from minerva.triage.router import TriageRouter

        config = MinervaConfig.load()
        llm = OpenAICompatibleClient(base_url=config.llm.base_url, model=config.llm.models["agent"])
        search = SearchEngine({
            "searxng_url": config.search.searxng_url,
            "metaso_api_key": config.search.metaso_api_key,
            "exa_api_key": config.search.exa_api_key,
        })
        pipeline = create_default_pipeline(llm, search, None, None)
        triage = TriageRouter(llm)
        kb = SQLiteKnowledgeStore()
        cost_guard = CostGuard(monthly_budget=config.execution.monthly_budget_usd)
        _executor_ref["executor"] = ResearchExecutor(
            triage_router=triage, pipeline=pipeline, knowledge_store=kb, cost_guard=cost_guard,
        )
    except Exception:
        _executor_ref["executor"] = None
    yield
    _executor_ref.clear()


app = FastAPI(title="Minerva Deep Research", version="0.10.0", lifespan=lifespan,
              docs_url="/docs", openapi_url="/openapi.json")

# Apply security middleware
from minerva.web.middleware import APIKeyMiddleware, InputGuardMiddleware, RateLimitMiddleware
app.add_middleware(InputGuardMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(APIKeyMiddleware)


# -- Health ------------------------------------------------------------

@app.get("/health")
async def health():
    """System health check with component status."""
    checks = {
        "sqlite": _check_sqlite(),
        "llm_local": _check_llm_local(),
    }
    all_ok = all(v for v in checks.values())
    return {"status": "ok" if all_ok else "degraded", "checks": checks}


_health_sqlite_ok: bool | None = None  # Cache health check result

def _check_sqlite() -> bool:
    global _health_sqlite_ok
    if _health_sqlite_ok is not None:
        return _health_sqlite_ok
    try:
        import sqlite3
        conn = sqlite3.connect(":memory:")
        conn.execute("SELECT 1")
        conn.close()
        _health_sqlite_ok = True
    except Exception:
        _health_sqlite_ok = False
    return _health_sqlite_ok


def _check_llm_local() -> bool:
    try:
        from minerva.config import MinervaConfig
        import httpx
        config = MinervaConfig.load()
        resp = httpx.get(f"{config.llm.base_url}/models", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


# -- Paradigm API -----------------------------------------------------

@app.get("/api/paradigm")
async def paradigm_analyze(query: str):
    """Analyze a research question and return the paradigm + suggested operations."""
    try:
        from sophia import compile_paradigm_sync
        prog = compile_paradigm_sync(query)
        from sophia.learner import ParadigmLearner
        learner = ParadigmLearner()
        suggestion = learner.suggest_paradigm(query)
        return {
            "query": query,
            "paradigm": prog.name,
            "operations": [op.value for op in prog.operations],
            "state_count": prog.state_count,
            "transition_count": len(prog.transitions),
            "mermaid": prog.to_mermaid(),
            "evolution": {
                "sample_count": suggestion.get("sample_count", 0),
                "confidence": suggestion.get("confidence", 0),
                "recommended_ops": suggestion.get("recommended_ops", []),
                "top_traces": suggestion.get("top_traces", [])[:3],
            } if suggestion.get("sample_count", 0) > 0 else None,
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# -- SSE Progress Stream ----------------------------------------------

@app.get("/api/stream")
async def progress_stream():
    """Server-Sent Events stream for real-time system status."""
    from starlette.responses import StreamingResponse
    import asyncio, json

    async def event_stream():
        while True:
            checks = {
                "sqlite": _check_sqlite(),
                "llm": _check_llm_local(),
                "executor": _executor_ref.get("executor") is not None,
            }
            yield f"data: {json.dumps({'status': 'ok' if all(checks.values()) else 'degraded', 'checks': checks})}\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# -- Research API ------------------------------------------------------

@app.post("/api/research")
async def research_start(query: str = Form(...), level: str = Form("auto"), max_cost: float = Form(1.0)):
    """Start a research task. Returns task_id for polling."""
    executor = _executor_ref.get("executor")
    if executor is None:
        return JSONResponse({"error": "Executor not initialized"}, status_code=503)
    task_id = str(uuid.uuid4())[:8]
    from minerva.executor.executor import ExecutionMode, ResearchTask
    task = ResearchTask(id=task_id, query=query, mode=ExecutionMode.IMMEDIATE, level=level, max_cost=max_cost)
    try:
        result = await executor.execute_now(task)
        # Enrich response with paradigm analysis
        try:
            from sophia import compile_paradigm_sync
            prog = compile_paradigm_sync(query)
            paradigm_info = {
                "paradigm": prog.name,
                "operations": [op.value for op in prog.operations],
                "state_count": prog.state_count,
                "transition_count": len(prog.transitions),
                "mermaid": prog.to_mermaid(),
            }
        except Exception:
            paradigm_info = None
        # Include stage timings for pipeline visualization
        stage_timings = result.context.stage_timings if hasattr(result, 'context') else {}

        return {
            "task_id": task_id, "status": "completed",
            "query": query,
            "level": level,
            "summary": result.summary[:800], "report_path": result.report_path, "cost": result.cost,
            "paradigm": paradigm_info,
            "stages": {name: round(elapsed, 2) for name, elapsed in stage_timings.items()},
            "total_time": round(sum(stage_timings.values()), 2) if stage_timings else 0,
        }
    except Exception as e:
        return JSONResponse({"task_id": task_id, "status": "failed", "error": str(e)[:300]}, status_code=500)


@app.get("/api/research/{task_id}")
async def research_status(task_id: str):
    executor = _executor_ref.get("executor")
    if executor is None:
        return JSONResponse({"error": "Executor not initialized"}, status_code=503)
    status = await executor.get_status(task_id)
    return {"task_id": task_id, "found": status is not None}


@app.get("/api/progress")
async def system_progress():
    """Return current system state for dashboard polling."""
    executor = _executor_ref.get("executor")
    checks = {
        "sqlite": _check_sqlite(),
        "llm_local": _check_llm_local(),
        "executor": executor is not None,
    }
    return {
        "status": "ok" if all(checks.values()) else "degraded",
        "checks": checks,
        "timestamp": __import__("time").strftime("%H:%M:%S"),
    }


# -- Report Export (PDF) ---------------------------------------------

@app.get("/api/report/pdf")
async def export_pdf(path: str = ""):
    """Export a research report as print-ready HTML."""
    from pathlib import Path as _Path
    fp = _Path(path).expanduser()
    if not fp.exists():
        return JSONResponse({"error": "Report not found"}, status_code=404)
    try:
        from minerva.web.export import markdown_to_html
        html = markdown_to_html(str(fp))
        return HTMLResponse(html)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# -- Report Rendering -------------------------------------------------

@app.get("/api/report")
async def view_report(path: str = ""):
    """Render a research report as styled HTML from markdown."""
    from pathlib import Path as _Path
    fp = _Path(path).expanduser()
    if not fp.exists():
        return JSONResponse({"error": "Report not found", "path": str(fp)}, status_code=404)
    try:
        md = fp.read_text()
        html = _md_to_html(md)
        return HTMLResponse(REPORT_WRAPPER.format(title=fp.name, content=html))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


def _md_to_html(md: str) -> str:
    """Simple markdown to HTML converter (no external dependency)."""
    import re
    lines = md.split('\n')
    out = []
    in_table = False
    i = 0
    while i < len(lines):
        line = lines[i]
        # Headers
        if line.startswith('### '):
            out.append(f'<h3>{_esc(line[4:])}</h3>')
        elif line.startswith('## '):
            out.append(f'<h2>{_esc(line[3:])}</h2>')
        elif line.startswith('# '):
            out.append(f'<h1>{_esc(line[2:])}</h1>')
        # Blockquote
        elif line.startswith('> '):
            out.append(f'<blockquote>{_fmt_inline(line[2:])}</blockquote>')
        # Horizontal rule
        elif line.strip() == '---':
            out.append('<hr>')
        # Table
        elif line.startswith('|'):
            if not in_table:
                out.append('<table>')
                in_table = True
            cells = [c.strip() for c in line.split('|')[1:-1]]
            is_header = all(c.startswith('-') or c.startswith(':') for c in cells if c)
            if not is_header:
                tag = 'th' if i+1 < len(lines) and lines[i+1].startswith('|') and '-' in lines[i+1] else 'td'
                out.append('<tr>' + ''.join(f'<{tag}>{_fmt_inline(c)}</{tag}>' for c in cells) + '</tr>')
        elif in_table and not line.startswith('|'):
            out.append('</table>')
            in_table = False
        # Ordered list
        elif re.match(r'^\d+\.\s+', line):
            cleaned = re.sub(r'^\d+\.\s+', '', line)
            out.append(f'<li>{_fmt_inline(cleaned)}</li>')
        # Unordered list
        elif line.startswith('- ') or line.startswith('* '):
            out.append(f'<li>{_fmt_inline(line[2:])}</li>')
        # Code block (inline only for now)
        elif line.startswith('```'):
            out.append('<pre><code>')
            i += 1
            while i < len(lines) and not lines[i].startswith('```'):
                out.append(_esc(lines[i]))
                i += 1
            out.append('</code></pre>')
        # Bold/italic inline
        elif line.strip():
            out.append(f'<p>{_fmt_inline(line)}</p>')
        else:
            out.append('<br>')
        i += 1
    if in_table:
        out.append('</table>')
    return '\n'.join(out)


def _fmt_inline(text: str) -> str:
    """Format inline markdown: bold, italic, code, links."""
    import re
    text = _esc(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank">\1</a>', text)
    return text


def _esc(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


REPORT_WRAPPER = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title}</title>
<style>
:root{{--bg:#09090b;--surface:#1a1a1f;--text:#e4e4e9;--muted:#71717a;--gold:#f5a623;--blue:#60a5fa;--green:#22c55e;--red:#ef4444;--border:#252530}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'SF Pro Display','Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);padding:40px;max-width:860px;margin:0 auto;line-height:1.8;-webkit-font-smoothing:antialiased}}
h1{{font-size:1.8rem;color:var(--gold);margin:24px 0 12px;border-bottom:1px solid var(--border);padding-bottom:8px}}
h2{{font-size:1.3rem;color:var(--blue);margin:28px 0 10px;border-bottom:1px solid var(--border);padding-bottom:6px}}
h3{{font-size:1.1rem;color:var(--text);margin:20px 0 8px}}
blockquote{{border-left:3px solid var(--gold);padding:8px 16px;margin:12px 0;color:var(--muted);background:var(--surface);border-radius:0 8px 8px 0}}
p{{margin:8px 0;font-size:0.95rem}}
a{{color:var(--blue);text-decoration:none}}a:hover{{text-decoration:underline}}
code{{background:var(--surface);padding:2px 6px;border-radius:4px;font-size:0.88em;color:var(--green)}}
pre{{background:var(--surface);padding:16px;border-radius:8px;overflow-x:auto;margin:12px 0;border:1px solid var(--border)}}
pre code{{background:none;padding:0;color:var(--text)}}
table{{width:100%;border-collapse:collapse;margin:14px 0;font-size:0.88rem}}
th{{background:var(--surface);padding:10px;text-align:left;font-weight:600;border-bottom:2px solid var(--border);color:var(--gold)}}
td{{padding:10px;border-bottom:1px solid var(--border)}}
tr:hover td{{background:rgba(245,166,35,.03)}}
li{{margin:4px 0 4px 20px}}
hr{{border:none;border-top:1px solid var(--border);margin:20px 0}}
strong{{color:var(--gold);font-weight:600}}
em{{color:var(--muted)}}
@media(max-width:640px){{body{{padding:20px}}h1{{font-size:1.4rem}}}}
</style></head><body>{content}</body></html>"""


# -- Dashboard ---------------------------------------------------------

_DASHBOARD_PATH = __import__("pathlib").Path(__file__).parent / "dashboard.html"

def _load_dashboard() -> str:
    try:
        return _DASHBOARD_PATH.read_text()
    except Exception:
        return "<html><body><h1>Dashboard unavailable</h1></body></html>"


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(_load_dashboard())


