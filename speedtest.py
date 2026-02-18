#!/usr/bin/env python3
"""
Speedtest CLI -- advanced network speed testing from the terminal.

Usage::

    python speedtest.py              # rich dashboard
    python speedtest.py --simple     # plain text
    python speedtest.py --json       # JSON to stdout
    python speedtest.py -o result.json  # save to file
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Optional

from client.api import SpeedtestAPI
from client.constants import (
    DEFAULT_CONNECTIONS,
    DEFAULT_DURATION,
    DEFAULT_PING_COUNT,
    MAX_CONNECTIONS,
    MAX_DURATION,
    MAX_PING_COUNT,
    MIN_CONNECTIONS,
    MIN_DURATION,
    MIN_PING_COUNT,
)
from client.download import DownloadTester
from client.latency import LatencyTester
from client.upload import UploadTester
from ui.dashboard import (
    ProgressDisplay,
    console,
    print_client_info,
    print_final_results,
    print_header,
    print_latency_details,
    print_server_selection,
    print_speed_result,
)
from ui.output import create_result_json, save_json


# ---------------------------------------------------------------------------
# Parameter validation
# ---------------------------------------------------------------------------

def _validate(
    ping_count: int,
    download_duration: float,
    upload_duration: float,
    connections: int,
) -> None:
    """Raise ``ValueError`` if any parameter is out of range."""
    if not MIN_PING_COUNT <= ping_count <= MAX_PING_COUNT:
        raise ValueError(f"Ping count must be between {MIN_PING_COUNT} and {MAX_PING_COUNT}")
    if not MIN_DURATION <= download_duration <= MAX_DURATION:
        raise ValueError(f"Download duration must be between {MIN_DURATION} and {MAX_DURATION} s")
    if not MIN_DURATION <= upload_duration <= MAX_DURATION:
        raise ValueError(f"Upload duration must be between {MIN_DURATION} and {MAX_DURATION} s")
    if not MIN_CONNECTIONS <= connections <= MAX_CONNECTIONS:
        raise ValueError(f"Connections must be between {MIN_CONNECTIONS} and {MAX_CONNECTIONS}")


# ---------------------------------------------------------------------------
# Core test runner
# ---------------------------------------------------------------------------

async def run_speedtest(
    *,
    json_output: bool = False,
    output_file: Optional[str] = None,
    simple: bool = False,
    server_id: Optional[int] = None,
    ping_count: int = DEFAULT_PING_COUNT,
    download_duration: float = DEFAULT_DURATION,
    upload_duration: float = DEFAULT_DURATION,
    connections: int = DEFAULT_CONNECTIONS,
) -> Optional[dict]:
    """Execute the full speedtest sequence and return a JSON-serialisable dict."""

    show_ui = not json_output and not simple

    if show_ui:
        print_header()

    async with SpeedtestAPI() as api:

        # -- Client info ----------------------------------------------------
        if show_ui:
            console.print("[dim]Fetching client info...[/dim]")

        client_info = await api.get_client_info()

        if show_ui:
            print_client_info(
                ip=client_info.ip,
                isp=client_info.isp,
                location=client_info.country,
            )

        # -- Server list ----------------------------------------------------
        if show_ui:
            console.print("[dim]Fetching server list...[/dim]")

        servers = await api.fetch_servers(limit=10)

        if not servers:
            console.print("[red]Error: No servers available[/red]")
            return None

        if server_id:
            servers = [s for s in servers if s.id == server_id]
            if not servers:
                console.print(f"[red]Error: Server {server_id} not found[/red]")
                return None

        # -- Latency --------------------------------------------------------
        if show_ui:
            console.print("\n[bold]Testing latency to servers...[/bold]")

        latency_tester = LatencyTester(ping_count=ping_count)
        latency_results = await latency_tester.test_servers(servers)

        ok_results = [r for r in latency_results if r.success]
        if not ok_results:
            console.print("[red]Error: Could not connect to any servers[/red]")
            return None

        best = ok_results[0]
        best_server = best.server

        if show_ui:
            print_server_selection(latency_results, selected_idx=0)
            console.print(
                f"\n[green]Selected server:[/green] {best_server.name} ({best_server.sponsor})"
            )
            print_latency_details(best)

        # -- Download -------------------------------------------------------
        if show_ui:
            console.print("\n[bold]Testing download speed...[/bold]")
            progress = ProgressDisplay()
            progress.start("Downloading")

        dl_tester = DownloadTester(duration_seconds=download_duration)
        if show_ui:
            dl_tester.on_progress = lambda p, s: progress.update(p, s)

        dl_result = await dl_tester.test(best_server, connections=connections)

        if show_ui:
            progress.stop()
            print_speed_result(dl_result, "Download Results", "green")

        # -- Upload ---------------------------------------------------------
        if show_ui:
            console.print("\n[bold]Testing upload speed...[/bold]")
            progress = ProgressDisplay()
            progress.start("Uploading")

        ul_tester = UploadTester(duration_seconds=upload_duration)
        if show_ui:
            ul_tester.on_progress = lambda p, s: progress.update(p, s)

        ul_result = await ul_tester.test(best_server, connections=connections)

        if show_ui:
            progress.stop()
            print_speed_result(ul_result, "Upload Results", "blue")

        # -- Summary --------------------------------------------------------
        if show_ui:
            print_final_results(
                ping_ms=best.latency_ms,
                jitter_ms=best.jitter_ms,
                download_mbps=dl_result.speed_mbps,
                upload_mbps=ul_result.speed_mbps,
                server_name=best_server.name,
                server_sponsor=best_server.sponsor,
            )
        elif simple:
            print(f"Ping: {best.latency_ms:.1f} ms")
            print(f"Download: {dl_result.speed_mbps:.2f} Mbps")
            print(f"Upload: {ul_result.speed_mbps:.2f} Mbps")

        # -- JSON result ----------------------------------------------------
        result_json = create_result_json(
            client_info=client_info.to_dict(),
            server_info=best_server.to_dict(),
            latency_results=best.to_dict(),
            download_results=dl_result.to_dict(),
            upload_results=ul_result.to_dict(),
            server_selection=[r.to_dict() for r in latency_results[:10]],
        )

        if json_output:
            print(json.dumps(result_json, indent=2))

        if output_file:
            save_json(result_json, output_file)
            if not json_output:
                console.print(f"\n[green]Results saved to:[/green] {output_file}")

        return result_json


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Speedtest CLI -- Advanced network speed testing",
    )
    parser.add_argument("--json", "-j", action="store_true", help="Output results as JSON")
    parser.add_argument("--output", "-o", type=str, metavar="FILE", help="Save results to JSON file")
    parser.add_argument("--simple", "-s", action="store_true", help="Simple output mode (no dashboard)")
    parser.add_argument("--server", type=int, metavar="ID", help="Use specific server by ID")
    parser.add_argument("--ping-count", type=int, default=DEFAULT_PING_COUNT, metavar="N", help="Number of ping samples (default: 10)")
    parser.add_argument("--download-duration", type=float, default=DEFAULT_DURATION, metavar="SECS", help="Download test duration in seconds (default: 10)")
    parser.add_argument("--upload-duration", type=float, default=DEFAULT_DURATION, metavar="SECS", help="Upload test duration in seconds (default: 10)")
    parser.add_argument("--connections", type=int, default=DEFAULT_CONNECTIONS, metavar="N", help="Number of concurrent connections (default: 4)")
    parser.add_argument("--list-servers", action="store_true", help="List available servers and exit")

    args = parser.parse_args()

    # Validate
    try:
        _validate(
            ping_count=args.ping_count,
            download_duration=args.download_duration,
            upload_duration=args.upload_duration,
            connections=args.connections,
        )
    except ValueError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        sys.exit(1)

    # List-servers mode
    if args.list_servers:
        async def _list() -> None:
            async with SpeedtestAPI() as api:
                servers = await api.fetch_servers(limit=20)
                console.print("\n[bold]Available Servers:[/bold]\n")
                for s in servers:
                    console.print(
                        f"  {s.id:>6} | {s.name:<20} | {s.sponsor:<30} | {s.distance:.0f} km"
                    )
        asyncio.run(_list())
        return

    # Normal run
    try:
        asyncio.run(
            run_speedtest(
                json_output=args.json,
                output_file=args.output,
                simple=args.simple,
                server_id=args.server,
                ping_count=args.ping_count,
                download_duration=args.download_duration,
                upload_duration=args.upload_duration,
                connections=args.connections,
            )
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Test cancelled by user[/yellow]")
        sys.exit(1)
    except Exception as exc:
        console.print(f"\n[red]Error: {exc}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
