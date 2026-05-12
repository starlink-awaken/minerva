"""Rich terminal output — progress bars, colors, stage visualization."""

from __future__ import annotations

import time
from contextlib import contextmanager

try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
    from rich.table import Table
    from rich.panel import Panel
    from rich.live import Live
    from rich.layout import Layout
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

console = Console() if RICH_AVAILABLE else None


def print_banner():
    """Print Minerva startup banner."""
    if not RICH_AVAILABLE:
        print("=== Minerva Deep Research ===")
        return
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]Minerva[/bold cyan] [dim]— Local-First Deep Research[/dim]\n"
            "[dim]Ollama MLX · 7 Backends · Neo4j · spaCy · MCP[/dim]",
            border_style="cyan",
            padding=(1, 3),
        )
    )
    console.print()


def print_pipeline_header(query: str, level: str):
    """Print research pipeline start."""
    if not RICH_AVAILABLE:
        print(f"\nResearch: {query} [Level: {level}]")
        print("-" * 60)
        return
    console.print()
    console.print(f"  [bold]Query:[/bold] {query[:100]}")
    console.print(f"  [bold]Level:[/bold] [cyan]{level}[/cyan]  |  [bold]Backends:[/bold] [dim]DDG · Scholar · arXiv · Metaso · Exa[/dim]")
    console.print()


@contextmanager
def live_pipeline_display():
    """Show live pipeline progress."""
    if not RICH_AVAILABLE:
        yield None
        return

    layout = Layout()
    layout.split_column(
        Layout(name="header", size=1),
        Layout(name="stages", size=8),
        Layout(name="footer", size=1),
    )

    header = Panel("[bold]Research Pipeline[/bold]", style="cyan", padding=(0, 1))
    footer = Panel("[dim]Running...[/dim]", style="dim", padding=(0, 1))

    stage_info = {"stages": [], "current": ""}

    def render_stages():
        lines = []
        for s in stage_info["stages"][-7:]:
            icon = "✓" if s.get("done") else "◌"
            color = "green" if s.get("done") else "dim"
            elapsed = f"[dim]{s['elapsed']:.1f}s[/dim]" if s.get("elapsed") else ""
            lines.append(f"  [{color}]{icon} {s['name']:<20} {elapsed}[/{color}]")
        return Panel("\n".join(lines) if lines else "[dim]Initializing...[/dim]", border_style="blue")

    with Live(layout, refresh_per_second=4, transient=False) as live:
        layout["header"].update(header)
        layout["stages"].update(render_stages())
        layout["footer"].update(footer)

        class StageTracker:
            def add_stage(self, name, elapsed=0, done=False):
                stage_info["stages"].append({"name": name, "elapsed": elapsed, "done": done})
                stage_info["current"] = name
                layout["stages"].update(render_stages())

            def mark_done(self, name, elapsed=0):
                for s in stage_info["stages"]:
                    if s["name"] == name:
                        s["done"] = True
                        s["elapsed"] = elapsed
                        break
                layout["stages"].update(render_stages())
                completed = sum(1 for s in stage_info["stages"] if s["done"])
                total = len(stage_info["stages"])
                layout["footer"].update(
                    Panel(f"[dim]Completed: {completed}/{total}[/dim]", style="dim", padding=(0, 1))
                )

        yield StageTracker()


def print_summary_table(stage_timings: dict[str, float], quality_score: str, source_count: int, entity_count: int, total_time: float):
    """Print a rich summary table."""
    if not RICH_AVAILABLE:
        print(f"\nTotal: {total_time:.1f}s | Sources: {source_count} | Entities: {entity_count}")
        return

    table = Table(title="Pipeline Summary", box=box.ROUNDED, border_style="cyan")
    table.add_column("Stage", style="cyan")
    table.add_column("Time", justify="right", style="green")
    table.add_column("Bar", justify="left")

    max_time = max(stage_timings.values()) if stage_timings else 1
    for name, elapsed in stage_timings.items():
        bar_width = int(elapsed / max_time * 20)
        bar = "█" * bar_width + "░" * (20 - bar_width)
        table.add_row(name, f"{elapsed:.1f}s", f"[dim]{bar}[/dim]")

    table.add_row("─" * 15, "─" * 8, "─" * 22)
    table.add_row("[bold]TOTAL[/bold]", f"[bold green]{total_time:.1f}s[/bold green]", "")

    console.print()
    console.print(table)
    console.print(f"  [dim]Sources: {source_count}[/dim]  |  [dim]Entities: {entity_count}[/dim]  |  [bold]Score: {quality_score}/100[/bold]")
    console.print()
