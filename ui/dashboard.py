"""
Rich-based terminal dashboard for speedtest results.

All formatting helpers live in ``client.stats`` -- this module only does
presentation via the ``rich`` library.
"""
from __future__ import annotations

import statistics
from typing import List

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from client.stats import format_speed, format_latency

console = Console()


# ---------------------------------------------------------------------------
# Histogram helper
# ---------------------------------------------------------------------------

_BARS = "▁▂▃▄▅▆▇█"


def create_histogram(values: List[float], width: int = 40, height: int = 5) -> str:
    """Return a single-line Unicode bar-chart."""
    if not values:
        return "No data"

    lo, hi = min(values), max(values)
    span = hi - lo if hi > lo else 1.0
    norm = [(v - lo) / span * height for v in values]
    return "".join(_BARS[min(int(n * (len(_BARS) - 1) / height), len(_BARS) - 1)] for n in norm)


# ---------------------------------------------------------------------------
# Print helpers
# ---------------------------------------------------------------------------

def print_header() -> None:
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]Speedtest CLI[/bold cyan]\n"
            "[dim]Advanced network speed testing with detailed metrics[/dim]",
            border_style="cyan",
        )
    )
    console.print()


def print_client_info(ip: str, isp: str, location: str = "") -> None:
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="dim")
    table.add_column(style="bold")
    table.add_row("IP Address:", ip)
    table.add_row("ISP:", isp)
    if location:
        table.add_row("Location:", location)
    console.print(Panel(table, title="[bold]Client Info[/bold]", border_style="blue"))


def print_server_selection(servers: list, selected_idx: int = 0) -> None:
    table = Table(title="Server Selection", box=box.ROUNDED)
    table.add_column("#", style="dim", width=4)
    table.add_column("Server", style="bold")
    table.add_column("Sponsor")
    table.add_column("Distance", justify="right")
    table.add_column("Latency", justify="right")
    table.add_column("Jitter", justify="right")

    for i, result in enumerate(servers[:10]):
        style = "green" if i == selected_idx else None
        marker = ">" if i == selected_idx else " "
        table.add_row(
            f"{marker}{i + 1}",
            result.server.name,
            result.server.sponsor,
            f"{result.server.distance:.0f} km",
            format_latency(result.latency_ms) if result.success else "N/A",
            f"{result.jitter_ms:.2f} ms" if result.success else "N/A",
            style=style,
        )

    console.print(table)


def print_latency_details(result) -> None:  # noqa: ANN001 (ServerLatencyResult)
    """Print detailed latency statistics and a histogram."""
    table = Table(title="Latency Details", box=box.ROUNDED)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    pings = result.pings
    table.add_row("Min", format_latency(min(pings)))
    table.add_row("Max", format_latency(max(pings)))
    table.add_row("Mean", format_latency(statistics.mean(pings)))
    table.add_row("Median", format_latency(statistics.median(pings)))
    table.add_row("Jitter", f"{result.jitter_ms:.2f} ms")
    table.add_row("Samples", str(len(pings)))
    console.print(table)

    console.print(
        Panel(
            f"[cyan]{create_histogram(pings, width=len(pings))}[/cyan]\n"
            f"[dim]Min: {min(pings):.1f} ms  Max: {max(pings):.1f} ms[/dim]",
            title="Ping Histogram",
        )
    )


def print_speed_result(result, title: str, color: str = "green") -> None:  # noqa: ANN001
    """Print a download or upload result panel."""
    table = Table(title=title, box=box.ROUNDED)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Speed", f"[bold {color}]{format_speed(result.speed_mbps)}[/bold {color}]")
    table.add_row("Data Transferred", f"{result.bytes_total / 1_000_000:.1f} MB")
    table.add_row("Duration", f"{result.duration_ms / 1000:.1f} s")
    table.add_row("Connections", str(len(result.connections)))
    console.print(table)

    if result.samples:
        console.print(
            Panel(
                f"[{color}]{create_histogram(result.samples)}[/{color}]\n"
                f"[dim]Min: {min(result.samples):.1f} Mbps  "
                f"Max: {max(result.samples):.1f} Mbps[/dim]",
                title="Speed Over Time",
            )
        )

    if result.connections:
        ct = Table(title="Per-Connection Stats", box=box.SIMPLE)
        ct.add_column("ID", style="dim")
        ct.add_column("Server")
        ct.add_column("Bytes", justify="right")
        ct.add_column("Speed", justify="right")
        for conn in result.connections:
            ct.add_row(
                str(conn.id),
                conn.hostname[:30],
                f"{conn.bytes_transferred / 1_000_000:.1f} MB",
                format_speed(conn.speed_mbps),
            )
        console.print(ct)


def print_final_results(
    ping_ms: float,
    jitter_ms: float,
    download_mbps: float,
    upload_mbps: float,
    server_name: str,
    server_sponsor: str,
) -> None:
    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]Server:[/bold cyan] {server_name} ({server_sponsor})\n\n"
            f"[bold white]   Ping:[/bold white]  [bold yellow]{ping_ms:.1f} ms[/bold yellow]  "
            f"[dim](jitter: {jitter_ms:.2f} ms)[/dim]\n"
            f"[bold white]   Download:[/bold white]  [bold green]{format_speed(download_mbps)}[/bold green]\n"
            f"[bold white]   Upload:[/bold white]  [bold blue]{format_speed(upload_mbps)}[/bold blue]",
            title="[bold]Results[/bold]",
            border_style="cyan",
        )
    )
    console.print()


# ---------------------------------------------------------------------------
# Progress display
# ---------------------------------------------------------------------------

class ProgressDisplay:
    """Manages a ``rich`` progress bar during download / upload tests."""

    def __init__(self) -> None:
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description}"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("[bold cyan]{task.fields[speed]}[/bold cyan]"),
            TimeElapsedColumn(),
            console=console,
        )
        self._task_id = None
        self._last_speed = 0.0
        self._last_prog = 0.0

    def start(self, description: str) -> None:
        self.progress.start()
        self._task_id = self.progress.add_task(description, total=100, speed="")
        self._last_speed = 0.0
        self._last_prog = 0.0

    def update(self, progress: float, speed_mbps: float = 0) -> None:
        if self._task_id is None:
            return
        # Debounce: only update when values change noticeably
        if abs(progress - self._last_prog) < 0.01 and abs(speed_mbps - self._last_speed) < 1.0:
            return
        speed_str = format_speed(speed_mbps) if speed_mbps > 0 else "..."
        self.progress.update(self._task_id, completed=progress * 100, speed=speed_str)
        self._last_prog = progress
        self._last_speed = speed_mbps

    def stop(self) -> None:
        self.progress.stop()
