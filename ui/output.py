"""
Output formatting module for JSON export and text output.
"""
import json
from datetime import datetime
from typing import Dict, Any, Optional, List


def create_result_json(
    client_info: Dict[str, Any],
    server_info: Dict[str, Any],
    latency_results: Dict[str, Any],
    download_results: Dict[str, Any],
    upload_results: Dict[str, Any],
    server_selection: list = None
) -> Dict[str, Any]:
    """
    Create a comprehensive JSON result matching Ookla's format.
    Optimized to reduce redundant dictionary lookups.
    """
    # Cache frequently accessed values to reduce dictionary lookups
    pings = latency_results.get("pings", [])
    pings_count = len(pings)
    
    # Calculate RTT statistics once, with safety checks
    if pings and pings_count > 0:
        pings_sorted = sorted(pings)
        rtt_min = pings_sorted[0]
        rtt_max = pings_sorted[-1]
        rtt_mean = sum(pings) / pings_count
        rtt_median = pings_sorted[pings_count // 2]
    else:
        rtt_min = 0
        rtt_max = 0
        rtt_mean = 0
        rtt_median = 0
    
    result = {
        "timestamp": datetime.now().isoformat(),
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
                    "median": rtt_median
                },
                "count": pings_count,
                "samples": pings
            }
        },
        "download": {
            "speed_bps": download_results.get("speed_bps", 0),
            "speed_mbps": download_results.get("speed_mbps", 0),
            "bytes": download_results.get("bytes_total", 0),
            "duration_ms": download_results.get("duration_ms", 0),
            "connections": download_results.get("connections", []),
            "samples": download_results.get("samples", [])
        },
        "upload": {
            "speed_bps": upload_results.get("speed_bps", 0),
            "speed_mbps": upload_results.get("speed_mbps", 0),
            "bytes": upload_results.get("bytes_total", 0),
            "duration_ms": upload_results.get("duration_ms", 0),
            "connections": upload_results.get("connections", []),
            "samples": upload_results.get("samples", [])
        }
    }
    
    if server_selection:
        result["serverSelection"] = {
            "closestPingDetails": server_selection
        }
    
    return result


def save_json(result: Dict[str, Any], filepath: str):
    """Save result to JSON file with atomic write for safety."""
    import os
    import tempfile
    
    # Write to temporary file first, then rename for atomic operation
    # This prevents partial writes if the process is interrupted
    dir_path = os.path.dirname(filepath) or '.'
    temp_path = os.path.join(dir_path, f'.tmp_{os.path.basename(filepath)}')
    
    try:
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        # Atomic rename operation
        os.replace(temp_path, filepath)
    except (IOError, OSError) as e:
        # Clean up temp file if something went wrong
        if os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except:
                pass
        raise IOError(f"Failed to save JSON to {filepath}: {e}")


def format_text_result(
    ping_ms: float,
    jitter_ms: float,
    download_mbps: float,
    upload_mbps: float,
    server_name: str,
    isp: str,
    ip: str
) -> str:
    """Format a simple text result. Optimized for single string concatenation."""
    # Pre-calculate separator for reuse
    sep = "=" * 50
    mid_sep = "-" * 50
    
    # Build result string directly for better performance
    return (
        f"{sep}\n"
        f"Speedtest Results\n"
        f"{sep}\n"
        f"Server: {server_name}\n"
        f"ISP: {isp}\n"
        f"IP: {ip}\n"
        f"{mid_sep}\n"
        f"Ping: {ping_ms:.1f} ms (jitter: {jitter_ms:.2f} ms)\n"
        f"Download: {download_mbps:.2f} Mbps\n"
        f"Upload: {upload_mbps:.2f} Mbps\n"
        f"{sep}"
    )


def format_csv_header() -> str:
    """Return CSV header line."""
    return "timestamp,server,isp,ip,ping_ms,jitter_ms,download_mbps,upload_mbps"


def format_csv_row(
    server_name: str,
    isp: str,
    ip: str,
    ping_ms: float,
    jitter_ms: float,
    download_mbps: float,
    upload_mbps: float
) -> str:
    """Format a CSV row."""
    timestamp = datetime.now().isoformat()
    return f"{timestamp},{server_name},{isp},{ip},{ping_ms:.1f},{jitter_ms:.2f},{download_mbps:.2f},{upload_mbps:.2f}"
