"""
Statistics module for calculating network metrics.
"""
from dataclasses import dataclass, field
from typing import List
import statistics


@dataclass
class LatencyStats:
    """Latency statistics container."""
    samples: List[float] = field(default_factory=list)
    min: float = 0.0
    max: float = 0.0
    mean: float = 0.0
    median: float = 0.0
    iqm: float = 0.0  # Interquartile mean
    jitter: float = 0.0
    count: int = 0
    
    def calculate(self):
        """Calculate all statistics from samples."""
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
            "samples": self.samples,
            "min": round(self.min, 3),
            "max": round(self.max, 3),
            "mean": round(self.mean, 3),
            "median": round(self.median, 3),
            "iqm": round(self.iqm, 3),
            "jitter": round(self.jitter, 3),
            "count": self.count
        }


@dataclass
class SpeedStats:
    """Speed test statistics container."""
    bytes_transferred: int = 0
    duration_ms: float = 0.0
    speed_bps: float = 0.0  # bits per second
    speed_mbps: float = 0.0  # megabits per second
    samples: List[float] = field(default_factory=list)  # speed samples over time
    
    def calculate(self):
        """Calculate speed from bytes and duration."""
        if self.duration_ms > 0:
            self.speed_bps = (self.bytes_transferred * 8) / (self.duration_ms / 1000)
            self.speed_mbps = self.speed_bps / 1_000_000
    
    def to_dict(self) -> dict:
        return {
            "bytes": self.bytes_transferred,
            "duration_ms": round(self.duration_ms, 2),
            "speed_bps": round(self.speed_bps, 2),
            "speed_mbps": round(self.speed_mbps, 2),
            "samples": [round(s, 2) for s in self.samples]
        }


@dataclass
class ConnectionStats:
    """Per-connection statistics."""
    id: int = 0
    server_id: int = 0
    hostname: str = ""
    bytes_transferred: int = 0
    duration_ms: float = 0.0
    speed_mbps: float = 0.0
    speed_samples: List[float] = field(default_factory=list)  # Per-connection speed samples for aggregation
    
    def calculate(self):
        if self.duration_ms > 0:
            self.speed_mbps = (self.bytes_transferred * 8) / (self.duration_ms / 1000) / 1_000_000
    
    def to_dict(self) -> dict:
        result = {
            "id": self.id,
            "server_id": self.server_id,
            "hostname": self.hostname,
            "bytes": self.bytes_transferred,
            "duration_ms": round(self.duration_ms, 2),
            "speed_mbps": round(self.speed_mbps, 2)
        }
        # Only include speed_samples if non-empty
        if self.speed_samples:
            result["speed_samples"] = [round(s, 2) for s in self.speed_samples]
        return result


def calculate_jitter(samples: List[float]) -> float:
    """
    Calculate jitter as mean absolute difference between consecutive samples.
    This is how Ookla calculates jitter.
    """
    if len(samples) < 2:
        return 0.0
    
    differences = []
    for i in range(1, len(samples)):
        differences.append(abs(samples[i] - samples[i-1]))
    
    return statistics.mean(differences)


def calculate_iqm(samples: List[float]) -> float:
    """
    Calculate Interquartile Mean (IQM).
    Mean of values between 25th and 75th percentile.
    """
    if len(samples) < 4:
        return statistics.mean(samples) if samples else 0.0
    
    sorted_samples = sorted(samples)
    n = len(sorted_samples)
    q1_idx = n // 4
    q3_idx = (3 * n) // 4
    
    iqr_samples = sorted_samples[q1_idx:q3_idx]
    return statistics.mean(iqr_samples) if iqr_samples else 0.0


def calculate_percentile(samples: List[float], percentile: float) -> float:
    """Calculate the given percentile of samples."""
    if not samples:
        return 0.0
    
    sorted_samples = sorted(samples)
    n = len(sorted_samples)
    idx = (percentile / 100) * (n - 1)
    
    lower = int(idx)
    upper = lower + 1
    
    if upper >= n:
        return sorted_samples[-1]
    
    # Linear interpolation
    weight = idx - lower
    return sorted_samples[lower] * (1 - weight) + sorted_samples[upper] * weight


def format_speed(speed_bps: float) -> str:
    """Format speed in human-readable format."""
    if speed_bps >= 1_000_000_000:
        return f"{speed_bps / 1_000_000_000:.2f} Gbps"
    elif speed_bps >= 1_000_000:
        return f"{speed_bps / 1_000_000:.2f} Mbps"
    elif speed_bps >= 1_000:
        return f"{speed_bps / 1_000:.2f} Kbps"
    else:
        return f"{speed_bps:.2f} bps"


def format_latency(latency_ms: float) -> str:
    """Format latency in human-readable format."""
    if latency_ms >= 1000:
        return f"{latency_ms / 1000:.2f} s"
    else:
        return f"{latency_ms:.1f} ms"
