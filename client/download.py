"""
Download speed test module.

Uses parallel HTTPS GET streams against an Ookla server.  Design mirrors
the upload module: shared session, warm-up discard, IQM-based final speed,
and EMA-smoothed progress callback.
"""
from __future__ import annotations

import asyncio
import statistics
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import aiohttp

from .api import Server
from .constants import (
    CHUNK_SIZE,
    COMMON_HEADERS,
    DOWNLOAD_FILE_SIZE,
    EMA_ALPHA,
    MAX_CONNECTIONS,
    MAX_REASONABLE_SPEED,
    MIN_CONNECTIONS,
    SAMPLE_INTERVAL,
    WARMUP_SECONDS,
)
from .stats import ConnectionStats, LatencyStats


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class DownloadResult:
    """Download test result."""

    speed_bps: float = 0.0
    speed_mbps: float = 0.0
    bytes_total: int = 0
    duration_ms: float = 0.0
    connections: List[ConnectionStats] = field(default_factory=list)
    loaded_latency: Optional[LatencyStats] = None
    samples: List[float] = field(default_factory=list)

    def calculate(self) -> None:
        """Derive speed from total bytes and wall-clock duration."""
        if self.duration_ms > 0:
            self.speed_bps = (self.bytes_total * 8) / (self.duration_ms / 1000)
            self.speed_mbps = self.speed_bps / 1_000_000

    def calculate_from_samples(self) -> None:
        """Use interquartile mean of speed samples for a more stable result."""
        if not self.samples:
            self.calculate()
            return

        trimmed = _iqm(self.samples)
        if trimmed > 0:
            self.speed_mbps = trimmed
            self.speed_bps = trimmed * 1_000_000

    def to_dict(self) -> dict:
        result: dict = {
            "speed_bps": round(self.speed_bps, 2),
            "speed_mbps": round(self.speed_mbps, 2),
            "bytes_total": self.bytes_total,
            "duration_ms": round(self.duration_ms, 2),
            "connections": [c.to_dict() for c in self.connections],
            "samples": [round(s, 2) for s in self.samples],
        }
        if self.loaded_latency:
            result["loaded_latency"] = self.loaded_latency.to_dict()
        return result


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _iqm(samples: List[float]) -> float:
    if not samples:
        return 0.0
    if len(samples) < 4:
        return statistics.mean(samples)
    ordered = sorted(samples)
    n = len(ordered)
    return statistics.mean(ordered[n // 4 : (3 * n) // 4]) or statistics.mean(samples)


# ---------------------------------------------------------------------------
# Tester
# ---------------------------------------------------------------------------

class DownloadTester:
    """
    Parallel download speed tester.

    Each worker opens a long-running GET request and reads ``CHUNK_SIZE``
    chunks in a loop.  A sampler coroutine records throughput every
    ``SAMPLE_INTERVAL`` seconds, discarding the first ``WARMUP_SECONDS``.
    The final speed is the IQM of the post-warmup samples.
    """

    def __init__(self, duration_seconds: float = 10.0) -> None:
        self.duration_seconds = duration_seconds
        self.on_progress: Optional[Callable[[float, float], None]] = None

    async def test(self, server: Server, connections: int = 4) -> DownloadResult:
        connections = max(MIN_CONNECTIONS, min(connections, MAX_CONNECTIONS))

        result = DownloadResult()
        total_bytes = 0
        speed_samples: List[float] = []
        conn_stats: List[ConnectionStats] = []

        start_time = time.perf_counter()
        end_time = start_time + self.duration_seconds
        stop = asyncio.Event()

        # -- Worker ---------------------------------------------------------

        async def _worker(session: aiohttp.ClientSession, cid: int) -> None:
            nonlocal total_bytes

            stats = ConnectionStats(id=cid, server_id=server.id, hostname=server.hostname)
            conn_stats.append(stats)
            t0 = time.perf_counter()

            while not stop.is_set() and time.perf_counter() < end_time:
                try:
                    url = f"{server.download_url}?size={DOWNLOAD_FILE_SIZE}"
                    async with session.get(url) as resp:
                        while not stop.is_set():
                            if time.perf_counter() >= end_time:
                                break
                            try:
                                chunk = await asyncio.wait_for(
                                    resp.content.read(CHUNK_SIZE),
                                    timeout=1.0,
                                )
                            except asyncio.TimeoutError:
                                continue
                            if not chunk:
                                break

                            n = len(chunk)
                            stats.bytes_transferred += n
                            total_bytes += n

                except asyncio.CancelledError:
                    break
                except (aiohttp.ClientError, aiohttp.ClientPayloadError, OSError):
                    if stop.is_set():
                        break
                    await asyncio.sleep(0.2)

            stats.duration_ms = (time.perf_counter() - t0) * 1000
            stats.calculate()

        # -- Sampler --------------------------------------------------------

        async def _sampler() -> None:
            prev_bytes = 0
            prev_time = start_time
            smoothed = 0.0

            while not stop.is_set() and time.perf_counter() < end_time:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=SAMPLE_INTERVAL)
                    break
                except asyncio.TimeoutError:
                    pass

                now = time.perf_counter()
                cur = total_bytes
                dt = now - prev_time

                if dt < 0.05 or cur <= prev_bytes:
                    continue

                mbps = ((cur - prev_bytes) * 8) / dt / 1_000_000
                prev_bytes = cur
                prev_time = now

                if mbps > MAX_REASONABLE_SPEED:
                    continue

                if now - start_time >= WARMUP_SECONDS:
                    speed_samples.append(mbps)

                smoothed = (
                    mbps if smoothed == 0.0
                    else EMA_ALPHA * mbps + (1 - EMA_ALPHA) * smoothed
                )

                if self.on_progress:
                    prog = min((now - start_time) / self.duration_seconds, 1.0)
                    self.on_progress(prog, smoothed)

        # -- Orchestration --------------------------------------------------

        connector = aiohttp.TCPConnector(
            ssl=True,
            limit=connections,
            limit_per_host=connections,
            force_close=False,
            enable_cleanup_closed=True,
        )
        timeout = aiohttp.ClientTimeout(total=None, connect=5, sock_read=5)
        headers = {**COMMON_HEADERS, "Accept-Encoding": "identity"}

        async with aiohttp.ClientSession(
            headers=headers,
            connector=connector,
            timeout=timeout,
        ) as session:
            workers = [asyncio.create_task(_worker(session, i)) for i in range(connections)]
            sampler = asyncio.create_task(_sampler())

            remaining = end_time - time.perf_counter()
            if remaining > 0:
                await asyncio.sleep(remaining)

            stop.set()

            for t in workers:
                t.cancel()
            sampler.cancel()

            await asyncio.gather(*workers, return_exceptions=True)
            try:
                await sampler
            except (asyncio.CancelledError, RuntimeError):
                pass

        result.duration_ms = (time.perf_counter() - start_time) * 1000
        result.bytes_total = total_bytes
        result.connections = conn_stats
        result.samples = speed_samples
        result.calculate_from_samples()

        return result
