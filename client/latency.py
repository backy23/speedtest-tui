"""
WebSocket-based latency measurement using the Ookla Speedtest protocol.

Protocol flow::

    1. Connect to  wss://{hostname}:{port}/ws
    2. Receive  HELLO {version}
    3. Receive  YOURIP {ip}
    4. Receive  CAPABILITIES ...
    5. Send     PING {timestamp_ms}
    6. Receive  PONG {server_timestamp}
    7. Repeat 5-6 for the desired number of samples.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import List, Optional

import websockets
import websockets.exceptions

from .api import Server
from .constants import COMMON_HEADERS, DEFAULT_PING_COUNT
from .stats import calculate_jitter


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

_WS_CONNECT_TIMEOUT = 5.0   # seconds to establish the WS connection
_HANDSHAKE_TIMEOUT = 2.0     # max wait for HELLO/YOURIP/CAPABILITIES
_MSG_TIMEOUT = 0.5           # per-message timeout during handshake
_PING_TIMEOUT = 5.0          # per-ping round-trip timeout
_MAX_CONCURRENT = 10         # semaphore cap for parallel server tests


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PingResult:
    """A single PING/PONG round-trip."""

    latency_ms: float = 0.0
    server_timestamp: int = 0
    client_timestamp: float = 0.0
    success: bool = True
    error: Optional[str] = None


@dataclass
class ServerLatencyResult:
    """Aggregated latency data for one server."""

    server: Server
    external_ip: str = ""
    pings: List[float] = field(default_factory=list)
    latency_ms: float = 0.0     # best (min) latency
    jitter_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None
    server_version: str = ""

    def calculate(self) -> None:
        """Derive min-latency and jitter from collected pings."""
        if self.pings:
            self.latency_ms = min(self.pings)
            self.jitter_ms = calculate_jitter(self.pings)

    def to_dict(self) -> dict:
        return {
            "server_id": self.server.id,
            "server_name": self.server.name,
            "sponsor": self.server.sponsor,
            "external_ip": self.external_ip,
            "pings": [round(p, 1) for p in self.pings],
            "latency_ms": round(self.latency_ms, 1),
            "jitter_ms": round(self.jitter_ms, 3),
            "success": self.success,
            "server_version": self.server_version,
        }


# ---------------------------------------------------------------------------
# Tester
# ---------------------------------------------------------------------------

class LatencyTester:
    """Test ping latency to one or more Ookla servers over WebSocket."""

    def __init__(
        self,
        ping_count: int = DEFAULT_PING_COUNT,
        timeout: float = _PING_TIMEOUT,
    ) -> None:
        self.ping_count = ping_count
        self.timeout = timeout

    # -- Single server ------------------------------------------------------

    async def test_server(self, server: Server) -> ServerLatencyResult:
        result = ServerLatencyResult(server=server)

        try:
            async with websockets.connect(
                server.ws_url,
                additional_headers=COMMON_HEADERS,
                ping_interval=None,
                close_timeout=2,
                open_timeout=_WS_CONNECT_TIMEOUT,
            ) as ws:
                await self._read_handshake(ws, result)

                for _ in range(self.ping_count):
                    pr = await self._ping_once(ws)
                    if pr.success:
                        result.pings.append(pr.latency_ms)
                    else:
                        # One failure is tolerated; two in a row means stop.
                        pr2 = await self._ping_once(ws)
                        if pr2.success:
                            result.pings.append(pr2.latency_ms)
                        else:
                            break

                result.calculate()

        except asyncio.TimeoutError:
            result.success = False
            result.error = "Connection timeout"
        except (websockets.exceptions.WebSocketException, ConnectionError, OSError) as exc:
            result.success = False
            result.error = str(exc)

        return result

    # -- Multiple servers ---------------------------------------------------

    async def test_servers(
        self,
        servers: List[Server],
        concurrent: int = 1,
    ) -> List[ServerLatencyResult]:
        """Test *servers* and return results sorted by latency (best first)."""
        concurrent = max(1, min(concurrent, _MAX_CONCURRENT))

        if concurrent == 1:
            results = [await self.test_server(s) for s in servers]
        else:
            sem = asyncio.Semaphore(concurrent)

            async def _guarded(srv: Server) -> ServerLatencyResult:
                async with sem:
                    return await self.test_server(srv)

            results = await asyncio.gather(*[_guarded(s) for s in servers])

        results.sort(
            key=lambda r: (not r.success, r.latency_ms if r.success else float("inf"))
        )
        return results

    # -- Internals ----------------------------------------------------------

    @staticmethod
    async def _read_handshake(ws, result: ServerLatencyResult) -> None:
        """Consume HELLO / YOURIP / CAPABILITIES messages."""
        start = time.perf_counter()
        received = 0

        while time.perf_counter() - start < _HANDSHAKE_TIMEOUT:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=_MSG_TIMEOUT)
            except asyncio.TimeoutError:
                break
            except (websockets.exceptions.WebSocketException, ConnectionError, OSError):
                break

            if msg.startswith("HELLO"):
                parts = msg.split()
                if len(parts) >= 2:
                    result.server_version = parts[1]
            elif msg.startswith("YOURIP"):
                result.external_ip = msg.split()[1].strip()

            received += 1
            if received >= 3:
                break

    async def _ping_once(self, ws) -> PingResult:
        """Send PING, receive PONG, measure RTT."""
        send_time = time.perf_counter() * 1000  # ms
        await ws.send(f"PING {send_time}")

        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=self.timeout)
            recv_time = time.perf_counter() * 1000

            if msg.startswith("PONG"):
                parts = msg.split()
                server_ts = int(parts[1]) if len(parts) > 1 else 0
                return PingResult(
                    latency_ms=recv_time - send_time,
                    server_timestamp=server_ts,
                    client_timestamp=send_time,
                )
            return PingResult(
                success=False,
                client_timestamp=send_time,
                error=f"Unexpected response: {msg[:50]}",
            )
        except asyncio.TimeoutError:
            return PingResult(
                success=False,
                client_timestamp=send_time,
                error="Ping timeout",
            )
