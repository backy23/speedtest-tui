"""
Shared constants used across all client modules.

Centralises magic numbers, default headers, and tunables so they live in
exactly one place.
"""

# ---------------------------------------------------------------------------
# HTTP headers (browser-like, required by Ookla servers)
# ---------------------------------------------------------------------------

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
)

COMMON_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Origin": "https://www.speedtest.net",
    "Referer": "https://www.speedtest.net/",
}

# ---------------------------------------------------------------------------
# Speedtest.net endpoints
# ---------------------------------------------------------------------------

BASE_URL = "https://www.speedtest.net"
SERVERS_URL = "https://www.speedtest.net/api/js/servers"

# ---------------------------------------------------------------------------
# Connection limits
# ---------------------------------------------------------------------------

MIN_CONNECTIONS = 1
MAX_CONNECTIONS = 32
DEFAULT_CONNECTIONS = 4

# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------

DEFAULT_PING_COUNT = 10
DEFAULT_DURATION = 10.0          # seconds for download / upload
MIN_DURATION = 1.0
MAX_DURATION = 300.0
MIN_PING_COUNT = 1
MAX_PING_COUNT = 100

WARMUP_SECONDS = 2.0            # discard speed samples in this window
SAMPLE_INTERVAL = 0.25          # 250 ms between speed samples

# ---------------------------------------------------------------------------
# Data transfer
# ---------------------------------------------------------------------------

CHUNK_SIZE = 256 * 1024          # 256 KB – good TCP window utilisation
DOWNLOAD_FILE_SIZE = 50_000_000  # 50 MB request size
UPLOAD_BUFFER_SIZE = 1024 * 1024 # 1 MB pre-generated random buffer

# ---------------------------------------------------------------------------
# Speed filtering / smoothing
# ---------------------------------------------------------------------------

MAX_REASONABLE_SPEED = 20_000.0  # 20 Gbps – anything above is a spike
EMA_ALPHA = 0.25                 # exponential moving average weight
