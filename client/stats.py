"""
Network measurement statistics.

Pure functions and lightweight dataclasses -- no I/O, no side effects.
Everything here is deterministic and easy to unit-test.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class LatencyStats:
    """Aggregated latency statistics computed from a list of samples."""

    samples: List[float] = field(default_factory=list)
    min: float = 0.0
    max: float = 0.0
    mean: float = 0.0
    median: float = 0.0
    iqm: float = 0.0
    jitter: float = 0.0
    count: int = 0

    def calculate(self) -> None:
        if not self.samples:
            return
        self.count = len(self.samples)
        self.min = min(self.samples)
        self.max = max(self.samples)
        self.mean = statistics.mean(self.samples)
        self.median = statistics.median(self.samples)
        self.iqm = calculate_iqm(self.samples)
        self.jitter = calculate_jitter(self.samples)

    def to_dict(self) -> dict:
        return {
            "samples": [round(s, 3) for s in self.samples],
            "min": round(self.min, 3),
            "max": round(self.max, 3),
            "mean": round(self.mean, 3),
            "median": round(self.median, 3),
            "iqm": round(self.iqm, 3),
            "jitter": round(self.jitter, 3),
            "count": self.count,
        }


@dataclass
class SpeedStats:
    """Aggregated speed statistics."""

    bytes_transferred: int = 0
    duration_ms: float = 0.0
    speed_bps: float = 0.0
    speed_mbps: float = 0.0
    samples: List[float] = field(default_factory=list)

    def calculate(self) -> None:
        if self.duration_ms > 0:
            self.speed_bps = (self.bytes_transferred * 8) / (self.duration_ms / 1000)
            self.speed_mbps = self.speed_bps / 1_000_000

    def to_dict(self) -> dict:
        return {
            "bytes": self.bytes_transferred,
            "duration_ms": round(self.duration_ms, 2),
            "speed_bps": round(self.speed_bps, 2),
            "speed_mbps": round(self.speed_mbps, 2),
            "samples": [round(s, 2) for s in self.samples],
        }


@dataclass
class ConnectionStats:
    """Per-connection statistics collected by download / upload workers."""

    id: int = 0
    server_id: int = 0
    hostname: str = ""
    bytes_transferred: int = 0
    duration_ms: float = 0.0
    speed_mbps: float = 0.0

    def calculate(self) -> None:
        if self.duration_ms > 0:
            self.speed_mbps = (
                (self.bytes_transferred * 8) / (self.duration_ms / 1000) / 1_000_000
            )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "server_id": self.server_id,
            "hostname": self.hostname,
            "bytes": self.bytes_transferred,
            "duration_ms": round(self.duration_ms, 2),
            "speed_mbps": round(self.speed_mbps, 2),
        }


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------

def calculate_jitter(samples: List[float]) -> float:
    """Mean absolute difference between consecutive samples (Ookla method)."""
    if len(samples) < 2:
        return 0.0
    diffs = [abs(samples[i] - samples[i - 1]) for i in range(1, len(samples))]
    return statistics.mean(diffs)


def calculate_iqm(samples: List[float]) -> float:
    """Interquartile mean -- mean of values between Q1 and Q3."""
    if not samples:
        return 0.0
    if len(samples) < 4:
        return statistics.mean(samples)

    ordered = sorted(samples)
    n = len(ordered)
    q1 = n // 4
    q3 = (3 * n) // 4
    middle = ordered[q1:q3]
    return statistics.mean(middle) if middle else statistics.mean(samples)


def calculate_percentile(samples: List[float], percentile: float) -> float:
    """Linear-interpolation percentile."""
    if not samples:
        return 0.0

    ordered = sorted(samples)
    n = len(ordered)
    idx = (percentile / 100) * (n - 1)
    lower = int(idx)
    upper = min(lower + 1, n - 1)
    weight = idx - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def format_speed(speed_mbps: float) -> str:
    """Human-readable speed string."""
    if speed_mbps >= 1000:
        return f"{speed_mbps / 1000:.2f} Gbps"
    return f"{speed_mbps:.2f} Mbps"


def format_latency(latency_ms: float) -> str:
    """Human-readable latency string."""
    if latency_ms >= 1000:
        return f"{latency_ms / 1000:.2f} s"
    return f"{latency_ms:.1f} ms"
