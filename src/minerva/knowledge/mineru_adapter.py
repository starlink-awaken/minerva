"""MinerU adapter — high-quality document parsing for knowledge ingestion.

Uses MinerU CLI for PDF/DOCX/PPTX/XLSX parsing with 95+ accuracy.
Pipeline mode runs on pure CPU/MPS — no GPU/VRAM required.

Install: pip install "mineru[all]" (Python 3.10-3.13)
"""

from __future__ import annotations

import contextlib
import subprocess
from pathlib import Path

MINERU_VENV = Path(__file__).parent.parent.parent.parent / ".venv-mineru"


def is_available() -> bool:
    """Check if MinerU is installed in its venv."""
    mineru_bin = MINERU_VENV / "bin" / "mineru"
    return mineru_bin.exists()


def parse_document(
    input_path: str,
    output_dir: str | None = None,
    backend: str = "pipeline",
    method: str = "auto",
) -> dict:
    """Parse a document using MinerU pipeline mode.

    Args:
        input_path: Path to PDF, DOCX, PPTX, XLSX, or image file.
        output_dir: Output directory. Defaults to a temp dir.
        backend: 'pipeline' (CPU, 85+) | 'vlm-auto-engine' (GPU, 95+)
        method: 'auto' | 'txt' | 'ocr'

    Returns:
        {"status": "ok", "output_dir": "...", "files": [...]}
        or {"status": "error", "message": "..."}
    """
    if not is_available():
        return {"status": "error", "message": "MinerU not installed in .venv-mineru. Run: pip install \"mineru[all]\""}

    input_p = Path(input_path).expanduser()
    if not input_p.exists():
        return {"status": "error", "message": f"File not found: {input_path}"}

    output_p = Path(output_dir).expanduser() if output_dir else Path(input_p.stem + "_mineru_output")
    output_p = output_p.absolute()

    mineru_bin = MINERU_VENV / "bin" / "mineru"

    try:
        result = subprocess.run(
            [str(mineru_bin), "-p", str(input_p), "-o", str(output_p),
             "-b", backend, "-m", method],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return {"status": "error", "message": result.stderr[:500]}

        # Find generated markdown files
        md_files = list(output_p.rglob("*.md"))
        return {
            "status": "ok",
            "output_dir": str(output_p),
            "files": [str(f) for f in md_files],
            "count": len(md_files),
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "MinerU parsing timed out (120s)"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def parse_to_text(input_path: str) -> str:
    """Parse a document and return the combined markdown text.

    Convenience wrapper for ingest pipeline integration.
    """
    result = parse_document(input_path)
    if result["status"] != "ok":
        return ""

    texts = []
    for fpath in result.get("files", []):
        with contextlib.suppress(Exception):
            texts.append(Path(fpath).read_text())
    return "\n\n".join(texts)
