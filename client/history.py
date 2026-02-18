"""
Test history persistence and display.

Results are stored as JSON-lines in ``~/.speedtest-tui/history.jsonl``.
Each line is a self-contained JSON object with a timestamp, so the file
can be appended to safely (no need to parse the whole file to add a record).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_DIR = os.path.join(Path.home(), ".speedtest-tui")
_DEFAULT_FILE = "history.jsonl"
_MAX_DISPLAY = 20  # show last N entries in --history


def _history_path() -> str:
    return os.path.join(_DEFAULT_DIR, _DEFAULT_FILE)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def save_result(result: Dict[str, Any]) -> str:
    """Append *result* as a single JSON line.  Returns the file path."""
    path = _history_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # Ensure a timestamp exists
    if "timestamp" not in result:
        result["timestamp"] = datetime.now(timezone.utc).isoformat()

    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(result, ensure_ascii=False) + "\n")

    return path


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def load_history(limit: int = _MAX_DISPLAY) -> List[Dict[str, Any]]:
    """Return the most recent *limit* results, newest last."""
    path = _history_path()
    if not os.path.isfile(path):
        return []

    entries: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # skip corrupt lines

    return entries[-limit:]


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def format_history_table(entries: List[Dict[str, Any]]) -> List[dict]:
    """
    Transform raw history entries into a flat list of dicts suitable for
    tabular display.  Each dict has: timestamp, server, ping, download, upload.
    """
    rows = []
    for e in entries:
        ts_raw = e.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_raw).strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            ts = ts_raw[:16] if ts_raw else "?"

        server = e.get("server", {})
        server_name = server.get("name", "?")
        sponsor = server.get("sponsor", "")
        label = f"{server_name} ({sponsor})" if sponsor else server_name

        dl = e.get("download", {})
        ul = e.get("upload", {})

        rows.append({
            "timestamp": ts,
            "server": label,
            "ping": e.get("ping", 0),
            "jitter": e.get("jitter", 0),
            "download": dl.get("speed_mbps", 0),
            "upload": ul.get("speed_mbps", 0),
        })
    return rows


def sparkline(values: List[float]) -> str:
    """Single-line Unicode sparkline chart."""
    if not values:
        return ""
    bars = "▁▂▃▄▅▆▇█"
    lo, hi = min(values), max(values)
    span = hi - lo if hi > lo else 1.0
    return "".join(
        bars[min(int((v - lo) / span * (len(bars) - 1)), len(bars) - 1)]
        for v in values
    )
