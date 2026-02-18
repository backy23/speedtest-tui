"""
Output formatting -- JSON export, plain text, and CSV.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def create_result_json(
    client_info: Dict[str, Any],
    server_info: Dict[str, Any],
    latency_results: Dict[str, Any],
    download_results: Dict[str, Any],
    upload_results: Dict[str, Any],
    server_selection: Optional[List[dict]] = None,
) -> Dict[str, Any]:
    """Build a comprehensive JSON result dict matching Ookla's format."""
    pings: List[float] = latency_results.get("pings", [])
    n = len(pings)

    if pings:
        s = sorted(pings)
        rtt_min, rtt_max = s[0], s[-1]
        rtt_mean = sum(pings) / n
        rtt_median = s[n // 2]
    else:
        rtt_min = rtt_max = rtt_mean = rtt_median = 0

    result: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "client": client_info,
        "server": server_info,
        "ping": latency_results.get("latency_ms", 0),
        "jitter": latency_results.get("jitter_ms", 0),
        "pings": pings,
        "latency": {
            "connectionProtocol": "wss",
            "tcp": {
                "jitter": latency_results.get("jitter_ms", 0),
                "rtt": {
                    "min": rtt_min,
                    "max": rtt_max,
                    "mean": rtt_mean,
                    "median": rtt_median,
                },
                "count": n,
                "samples": pings,
            },
        },
        "download": {
            "speed_bps": download_results.get("speed_bps", 0),
            "speed_mbps": download_results.get("speed_mbps", 0),
            "bytes": download_results.get("bytes_total", 0),
            "duration_ms": download_results.get("duration_ms", 0),
            "connections": download_results.get("connections", []),
            "samples": download_results.get("samples", []),
        },
        "upload": {
            "speed_bps": upload_results.get("speed_bps", 0),
            "speed_mbps": upload_results.get("speed_mbps", 0),
            "bytes": upload_results.get("bytes_total", 0),
            "duration_ms": upload_results.get("duration_ms", 0),
            "connections": upload_results.get("connections", []),
            "samples": upload_results.get("samples", []),
        },
    }

    if server_selection:
        result["serverSelection"] = {"closestPingDetails": server_selection}

    return result


def save_json(result: Dict[str, Any], filepath: str) -> None:
    """Write *result* to *filepath* atomically (write-tmp then rename)."""
    dir_path = os.path.dirname(filepath) or "."
    tmp = os.path.join(dir_path, f".tmp_{os.path.basename(filepath)}")

    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, filepath)
    except (IOError, OSError) as exc:
        # Clean up partial temp file
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise IOError(f"Failed to save JSON to {filepath}: {exc}") from exc


# ---------------------------------------------------------------------------
# Plain-text / CSV helpers
# ---------------------------------------------------------------------------

def format_text_result(
    ping_ms: float,
    jitter_ms: float,
    download_mbps: float,
    upload_mbps: float,
    server_name: str,
    isp: str,
    ip: str,
) -> str:
    sep = "=" * 50
    mid = "-" * 50
    return (
        f"{sep}\n"
        f"Speedtest Results\n"
        f"{sep}\n"
        f"Server: {server_name}\n"
        f"ISP: {isp}\n"
        f"IP: {ip}\n"
        f"{mid}\n"
        f"Ping: {ping_ms:.1f} ms (jitter: {jitter_ms:.2f} ms)\n"
        f"Download: {download_mbps:.2f} Mbps\n"
        f"Upload: {upload_mbps:.2f} Mbps\n"
        f"{sep}"
    )


def format_csv_header() -> str:
    return "timestamp,server,isp,ip,ping_ms,jitter_ms,download_mbps,upload_mbps"


def format_csv_row(
    server_name: str,
    isp: str,
    ip: str,
    ping_ms: float,
    jitter_ms: float,
    download_mbps: float,
    upload_mbps: float,
) -> str:
    ts = datetime.now(timezone.utc).isoformat()
    return f"{ts},{server_name},{isp},{ip},{ping_ms:.1f},{jitter_ms:.2f},{download_mbps:.2f},{upload_mbps:.2f}"
