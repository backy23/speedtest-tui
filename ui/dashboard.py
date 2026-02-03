"""
Rich-based terminal dashboard for speedtest results.
"""
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.text import Text
from rich.style import Style
from rich import box
from typing import Optional, List
import statistics


console = Console()


def format_speed(speed_mbps: float) -> str:
    """Format speed with appropriate unit."""
    if speed_mbps >= 1000:
        return f"{speed_mbps / 1000:.2f} Gbps"
    else:
        return f"{speed_mbps:.2f} Mbps"


def format_latency(latency_ms: float) -> str:
    """Format latency."""
    return f"{latency_ms:.1f} ms"


def create_histogram(values: List[float], width: int = 40, height: int = 5) -> str:
    """
    Create a simple ASCII histogram.
    """
    if not values:
        return "No data"
    
    min_val = min(values)
    max_val = max(values)
    range_val = max_val - min_val if max_val > min_val else 1
    
    # Normalize values to height
    normalized = [(v - min_val) / range_val * height for v in values]
    
    # Create bars
    bars = "▁▂▃▄▅▆▇█"
    
    result = []
    for v in normalized:
        bar_idx = min(int(v * (len(bars) - 1) / height), len(bars) - 1)
        result.append(bars[bar_idx])
    
    return "".join(result)


def print_header():
    """Print the speedtest header."""
    console.print()
    console.print(Panel.fit(
        "[bold cyan]🚀 Speedtest CLI[/bold cyan]\n"
        "[dim]Advanced network speed testing with detailed metrics[/dim]",
        border_style="cyan"
    ))
    console.print()


def print_client_info(ip: str, isp: str, location: str = ""):
    """Print client information."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="dim")
    table.add_column(style="bold")
    
    table.add_row("IP Address:", ip)
    table.add_row("ISP:", isp)
    if location:
        table.add_row("Location:", location)
    
    console.print(Panel(table, title="[bold]Client Info[/bold]", border_style="blue"))


def print_server_selection(servers: list, selected_idx: int = 0):
    """Print server selection results."""
    table = Table(title="Server Selection", box=box.ROUNDED)
    table.add_column("#", style="dim", width=4)
    table.add_column("Server", style="bold")
    table.add_column("Sponsor")
    table.add_column("Distance", justify="right")
    table.add_column("Latency", justify="right")
    table.add_column("Jitter", justify="right")
    
    for i, result in enumerate(servers[:10]):
        style = "green" if i == selected_idx else None
        marker = "→" if i == selected_idx else " "
        
        table.add_row(
            f"{marker}{i+1}",
            result.server.name,
            result.server.sponsor,
            f"{result.server.distance:.0f} km",
            f"{result.latency_ms:.1f} ms" if result.success else "N/A",
            f"{result.jitter_ms:.2f} ms" if result.success else "N/A",
            style=style
        )
    
    console.print(table)


def print_latency_details(result):
    """Print detailed latency information with histogram."""
    table = Table(title="Latency Details", box=box.ROUNDED)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    
    table.add_row("Min", f"{min(result.pings):.1f} ms")
    table.add_row("Max", f"{max(result.pings):.1f} ms")
    table.add_row("Mean", f"{statistics.mean(result.pings):.1f} ms")
    table.add_row("Median", f"{statistics.median(result.pings):.1f} ms")
    table.add_row("Jitter", f"{result.jitter_ms:.2f} ms")
    table.add_row("Samples", str(len(result.pings)))
    
    console.print(table)
    
    # Print histogram
    console.print(Panel(
        f"[cyan]{create_histogram(result.pings, width=len(result.pings))}[/cyan]\n"
        f"[dim]Min: {min(result.pings):.1f} ms  Max: {max(result.pings):.1f} ms[/dim]",
        title="Ping Histogram"
    ))


def print_speed_result(result, title: str, color: str = "green"):
    """Print speed test result with details."""
    table = Table(title=title, box=box.ROUNDED)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    
    table.add_row("Speed", f"[bold {color}]{format_speed(result.speed_mbps)}[/bold {color}]")
    table.add_row("Data Transferred", f"{result.bytes_total / 1_000_000:.1f} MB")
    table.add_row("Duration", f"{result.duration_ms / 1000:.1f} s")
    table.add_row("Connections", str(len(result.connections)))
    
    console.print(table)
    
    # Speed histogram
    if result.samples:
        console.print(Panel(
            f"[{color}]{create_histogram(result.samples)}[/{color}]\n"
            f"[dim]Min: {min(result.samples):.1f} Mbps  Max: {max(result.samples):.1f} Mbps[/dim]",
            title="Speed Over Time"
        ))
    
    # Per-connection stats
    if result.connections:
        conn_table = Table(title="Per-Connection Stats", box=box.SIMPLE)
        conn_table.add_column("ID", style="dim")
        conn_table.add_column("Server")
        conn_table.add_column("Bytes", justify="right")
        conn_table.add_column("Speed", justify="right")
        
        for conn in result.connections:
            conn_table.add_row(
                str(conn.id),
                conn.hostname[:30],
                f"{conn.bytes_transferred / 1_000_000:.1f} MB",
                f"{conn.speed_mbps:.2f} Mbps"
            )
        
        console.print(conn_table)


def print_final_results(
    ping_ms: float,
    jitter_ms: float,
    download_mbps: float,
    upload_mbps: float,
    server_name: str,
    server_sponsor: str
):
    """Print final summary results."""
    console.print()
    console.print(Panel.fit(
        f"[bold cyan]Server:[/bold cyan] {server_name} ({server_sponsor})\n\n"
        f"[bold white]   Ping:[/bold white]  [bold yellow]{ping_ms:.1f} ms[/bold yellow]  "
        f"[dim](jitter: {jitter_ms:.2f} ms)[/dim]\n"
        f"[bold white]   Download:[/bold white]  [bold green]{format_speed(download_mbps)}[/bold green]\n"
        f"[bold white]   Upload:[/bold white]  [bold blue]{format_speed(upload_mbps)}[/bold blue]",
        title="[bold]📊 Results[/bold]",
        border_style="cyan"
    ))
    console.print()


class ProgressDisplay:
    """Manages progress display during tests."""
    
    def __init__(self):
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description}"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("•"),
            TextColumn("[bold cyan]{task.fields[speed]}[/bold cyan]"),
            TimeElapsedColumn(),
            console=console
        )
        self.task_id = None
        self._last_speed = 0.0  # Track last speed to reduce flicker
        self._last_progress = 0.0  # Track last progress to reduce updates
    
    def start(self, description: str):
        """Start progress display."""
        self.progress.start()
        self.task_id = self.progress.add_task(description, total=100, speed="")
        self._last_speed = 0.0
        self._last_progress = 0.0
    
    def update(self, progress: float, speed_mbps: float = 0):
        """Update progress with debouncing to reduce flicker."""
        if self.task_id is not None:
            # Only update if progress or speed changed significantly
            # This reduces UI updates and prevents flickering
            progress_changed = abs(progress - self._last_progress) >= 0.01  # 1% change
            speed_changed = abs(speed_mbps - self._last_speed) >= 1.0  # 1 Mbps change
            
            if progress_changed or speed_changed:
                speed_str = format_speed(speed_mbps) if speed_mbps > 0 else "..."
                self.progress.update(
                    self.task_id,
                    completed=progress * 100,
                    speed=speed_str
                )
                self._last_progress = progress
                self._last_speed = speed_mbps
    
    def stop(self):
        """Stop progress display."""
        self.progress.stop()


def print_json_result(result: dict):
    """Print formatted JSON result."""
    import json
    console.print_json(json.dumps(result, indent=2))
