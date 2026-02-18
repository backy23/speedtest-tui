"""
Speedtest.net API client.

Handles server discovery and client-info fetching.  All HTTP work goes
through a single ``aiohttp.ClientSession`` managed via async-context-manager
protocol (``async with SpeedtestAPI() as api: ...``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import aiohttp

from .constants import BASE_URL, COMMON_HEADERS, SERVERS_URL


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Server:
    """A single Ookla speedtest server."""

    id: int
    name: str
    sponsor: str
    hostname: str
    port: int
    country: str
    cc: str
    lat: float
    lon: float
    distance: float
    url: str
    https_functional: bool = True

    # -- Constructors -------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict) -> Server:
        host_raw = data.get("host", "")
        return cls(
            id=int(data.get("id", 0)),
            name=data.get("name", ""),
            sponsor=data.get("sponsor", ""),
            hostname=data.get("hostname", host_raw.split(":")[0]),
            port=int(data.get("port", 8080)),
            country=data.get("country", ""),
            cc=data.get("cc", ""),
            lat=float(data.get("lat", 0)),
            lon=float(data.get("lon", 0)),
            distance=float(data.get("distance", 0)),
            url=data.get("url", ""),
            https_functional=bool(data.get("httpsFunctional", True)),
        )

    # -- Derived URLs -------------------------------------------------------

    @property
    def ws_url(self) -> str:
        """WebSocket endpoint for latency testing."""
        return f"wss://{self.hostname}:{self.port}/ws?"

    @property
    def download_url(self) -> str:
        return f"https://{self.hostname}:{self.port}/download"

    @property
    def upload_url(self) -> str:
        return f"https://{self.hostname}:{self.port}/upload"

    # -- Serialisation ------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "sponsor": self.sponsor,
            "hostname": self.hostname,
            "port": self.port,
            "country": self.country,
            "cc": self.cc,
            "lat": self.lat,
            "lon": self.lon,
            "distance": self.distance,
        }


@dataclass
class ClientInfo:
    """Information about the client fetched from speedtest.net."""

    ip: str
    isp: str
    lat: float
    lon: float
    country: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ip": self.ip,
            "isp": self.isp,
            "lat": self.lat,
            "lon": self.lon,
            "country": self.country,
        }


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

class SpeedtestAPI:
    """Async context-manager wrapping the Speedtest.net REST API."""

    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None
        self.servers: List[Server] = []
        self.client_info: Optional[ClientInfo] = None

    # -- Context manager ----------------------------------------------------

    async def __aenter__(self) -> SpeedtestAPI:
        self._session = aiohttp.ClientSession(headers=COMMON_HEADERS)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        if self._session:
            await self._session.close()
            self._session = None

    # -- Internal helpers ---------------------------------------------------

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError(
                "SpeedtestAPI must be used as an async context manager "
                "(async with SpeedtestAPI() as api: ...)"
            )
        return self._session

    # -- Public methods -----------------------------------------------------

    async def get_client_info(self) -> ClientInfo:
        """Scrape client IP / ISP / location from the speedtest.net home page."""
        session = self._ensure_session()

        async with session.get(BASE_URL) as resp:
            resp.raise_for_status()
            html = await resp.text()

        def _extract(pattern: str) -> str:
            m = re.search(pattern, html)
            return m.group(1) if m else ""

        self.client_info = ClientInfo(
            ip=_extract(r'"ipAddress"\s*:\s*"([^"]+)"'),
            isp=_extract(r'"ispName"\s*:\s*"([^"]+)"'),
            lat=float(_extract(r'"latitude"\s*:\s*([\d.]+)') or 0),
            lon=float(_extract(r'"longitude"\s*:\s*([\d.]+)') or 0),
            country=_extract(r'"countryCode"\s*:\s*"([^"]+)"'),
        )
        return self.client_info

    async def fetch_servers(self, limit: int = 10) -> List[Server]:
        """Return up to *limit* nearby servers, sorted by distance."""
        session = self._ensure_session()

        params = {
            "engine": "js",
            "https_functional": "true",
            "limit": str(limit),
        }

        async with session.get(SERVERS_URL, params=params) as resp:
            resp.raise_for_status()
            data = await resp.json()

        self.servers = [Server.from_dict(s) for s in data]
        return self.servers
