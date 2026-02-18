"""
Upload speed test module.
Uses parallel HTTPS POST streaming to measure upload speed.

Key design decisions for accurate measurement:
- A shared aiohttp session avoids per-worker connection overhead.
- Bytes are counted as they are yielded to the async generator; aiohttp
  applies TCP back-pressure so yielded bytes closely match bytes on the wire.
- The first WARMUP_SECONDS of speed samples are discarded to ignore TCP
  slow-start and TLS negotiation noise.
- The final reported speed uses the interquartile mean (IQM) of the
  remaining samples, which is resistant to outlier spikes.
- The UI callback receives an exponentially-smoothed speed value to avoid
  visual flicker.
"""
import asyncio
import os
import statistics
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import aiohttp

from .api import Server
from .stats import ConnectionStats, LatencyStats

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

# Data generation
UPLOAD_CHUNK_SIZE = 256 * 1024        # 256 KB per yield – good for TCP window fill
UPLOAD_BUFFER_SIZE = 1024 * 1024      # 1 MB pre-generated random buffer

# Sampling
SAMPLE_INTERVAL = 0.25                # 250 ms – long enough for stable readings
WARMUP_SECONDS = 2.0                  # Discard samples during TCP slow-start

# Connections
MAX_CONNECTIONS = 32
MIN_CONNECTIONS = 1

# Speed filtering
MAX_REASONABLE_SPEED = 20_000.0       # 20 Gbps – anything above is a spike

# UI smoothing (exponential moving average)
EMA_ALPHA = 0.25                      # 25 % new value, 75 % previous


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class UploadResult:
    """Upload test result."""
    speed_bps: float = 0.0
    speed_mbps: float = 0.0
    bytes_total: int = 0
    duration_ms: float = 0.0
    connections: List[ConnectionStats] = field(default_factory=list)
    loaded_latency: Optional[LatencyStats] = None
    samples: List[float] = field(default_factory=list)

    def calculate(self):
        """Derive speed from total bytes and wall-clock duration."""
        if self.duration_ms > 0:
            self.speed_bps = (self.bytes_total * 8) / (self.duration_ms / 1000)
            self.speed_mbps = self.speed_bps / 1_000_000

    def calculate_from_samples(self):
        """
        Derive speed from the interquartile mean of collected samples.

        This is more accurate than total/duration because it filters out
        warm-up ramp and cool-down artefacts.
        """
        if not self.samples:
            self.calculate()
            return

        trimmed = _iqm_samples(self.samples)
        if trimmed > 0:
            self.speed_mbps = trimmed
            self.speed_bps = trimmed * 1_000_000

    def to_dict(self) -> dict:
        result = {
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
# Helper: interquartile mean
# ---------------------------------------------------------------------------

def _iqm_samples(samples: List[float]) -> float:
    """Return the interquartile mean of *samples*, or plain mean if < 4."""
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


# ---------------------------------------------------------------------------
# Tester
# ---------------------------------------------------------------------------

class UploadTester:
    """
    Upload speed tester using parallel HTTPS POST streams.

    Each worker opens a long-running streaming POST to the server.
    A shared ``aiohttp.ClientSession`` is used for connection pooling.
    Speed is sampled every ``SAMPLE_INTERVAL`` seconds; the first
    ``WARMUP_SECONDS`` of samples are discarded to avoid TCP slow-start
    noise.  The final speed is the interquartile mean of the remaining
    samples.
    """

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
        ),
        "Content-Type": "application/octet-stream",
        "Origin": "https://www.speedtest.net",
        "Referer": "https://www.speedtest.net/",
    }

    def __init__(self, duration_seconds: float = 15.0):
        self.duration_seconds = duration_seconds
        self._data_buffer = os.urandom(UPLOAD_BUFFER_SIZE)
        self.on_progress: Optional[Callable[[float, float], None]] = None

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def test(self, server: Server, connections: int = 4) -> UploadResult:
        """Run the upload speed test and return an ``UploadResult``."""
        connections = max(MIN_CONNECTIONS, min(connections, MAX_CONNECTIONS))

        result = UploadResult()

        # Shared mutable state -------------------------------------------
        total_bytes = 0                  # written by workers only
        speed_samples: List[float] = []  # written by sampler only
        conn_stats: List[ConnectionStats] = []

        start_time = time.perf_counter()
        end_time = start_time + self.duration_seconds
        stop = asyncio.Event()

        # ----------------------------------------------------------------
        # Worker coroutine
        # ----------------------------------------------------------------
        async def _worker(
            session: aiohttp.ClientSession,
            conn_id: int,
        ) -> None:
            nonlocal total_bytes

            stats = ConnectionStats(
                id=conn_id,
                server_id=server.id,
                hostname=server.hostname,
            )
            conn_stats.append(stats)
            worker_start = time.perf_counter()
            buf = self._data_buffer
            buf_len = len(buf)

            async def _data_stream():
                nonlocal total_bytes
                pos = 0
                while not stop.is_set() and time.perf_counter() < end_time:
                    # Slice a chunk out of the pre-generated buffer
                    end_pos = pos + UPLOAD_CHUNK_SIZE
                    if end_pos <= buf_len:
                        chunk = buf[pos:end_pos]
                        pos = end_pos
                    else:
                        chunk = buf[pos:] + buf[: end_pos - buf_len]
                        pos = end_pos - buf_len

                    chunk_len = len(chunk)
                    stats.bytes_transferred += chunk_len
                    total_bytes += chunk_len
                    yield chunk

                    # Yield to the event loop periodically so the sampler
                    # and stop-flag can run.
                    await asyncio.sleep(0)

            # Retry loop – reconnect if the server closes the POST early
            while not stop.is_set() and time.perf_counter() < end_time:
                try:
                    async with session.post(
                        server.upload_url,
                        data=_data_stream(),
                    ) as resp:
                        await resp.read()
                except asyncio.CancelledError:
                    break
                except (aiohttp.ClientError, OSError):
                    if stop.is_set():
                        break
                    await asyncio.sleep(0.2)

            stats.duration_ms = (time.perf_counter() - worker_start) * 1000
            stats.calculate()

        # ----------------------------------------------------------------
        # Sampler coroutine
        # ----------------------------------------------------------------
        async def _sampler() -> None:
            prev_bytes = 0
            prev_time = start_time
            smoothed: float = 0.0

            while not stop.is_set() and time.perf_counter() < end_time:
                try:
                    await asyncio.wait_for(
                        stop.wait(), timeout=SAMPLE_INTERVAL,
                    )
                    break  # stop was set
                except asyncio.TimeoutError:
                    pass

                now = time.perf_counter()
                cur_bytes = total_bytes
                dt = now - prev_time

                if dt < 0.05 or cur_bytes <= prev_bytes:
                    # Too little time or no new data – skip
                    continue

                instant_mbps = ((cur_bytes - prev_bytes) * 8) / dt / 1_000_000
                prev_bytes = cur_bytes
                prev_time = now

                # Drop absurd spikes (buffer-flush artefacts)
                if instant_mbps > MAX_REASONABLE_SPEED:
                    continue

                # Record sample only after warm-up
                elapsed = now - start_time
                if elapsed >= WARMUP_SECONDS:
                    speed_samples.append(instant_mbps)

                # Smooth for UI regardless of warm-up phase
                if smoothed == 0.0:
                    smoothed = instant_mbps
                else:
                    smoothed = EMA_ALPHA * instant_mbps + (1 - EMA_ALPHA) * smoothed

                if self.on_progress:
                    progress = min((now - start_time) / self.duration_seconds, 1.0)
                    self.on_progress(progress, smoothed)

        # ----------------------------------------------------------------
        # Orchestration
        # ----------------------------------------------------------------
        connector = aiohttp.TCPConnector(
            ssl=True,
            limit=connections,
            limit_per_host=connections,
            force_close=False,
            enable_cleanup_closed=True,
        )
        timeout = aiohttp.ClientTimeout(total=None, connect=5, sock_read=5)

        async with aiohttp.ClientSession(
            headers=self.HEADERS,
            connector=connector,
            timeout=timeout,
        ) as session:
            workers = [
                asyncio.create_task(_worker(session, i))
                for i in range(connections)
            ]
            sampler = asyncio.create_task(_sampler())

            # Sleep for the test duration
            remaining = end_time - time.perf_counter()
            if remaining > 0:
                await asyncio.sleep(remaining)

            # Signal everyone to stop
            stop.set()

            # Cancel workers so they don't hang on a POST
            for t in workers:
                t.cancel()
            sampler.cancel()

            await asyncio.gather(*workers, return_exceptions=True)
            try:
                await sampler
            except (asyncio.CancelledError, RuntimeError):
                pass

        # ----------------------------------------------------------------
        # Assemble result
        # ----------------------------------------------------------------
        result.duration_ms = (time.perf_counter() - start_time) * 1000
        result.bytes_total = total_bytes
        result.connections = conn_stats
        result.samples = speed_samples

        # Prefer IQM-of-samples over raw total/duration
        result.calculate_from_samples()

        return result
