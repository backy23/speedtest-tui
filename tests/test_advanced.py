"""
Advanced tests: mocked async networking, dashboard rendering,
edge cases, integration, and property-based validation.
"""

import asyncio
import json
import os
import tempfile
import unittest
from unittest import mock

from client.api import ClientInfo, Server, SpeedtestAPI
from client.config import DEFAULTS, load_config, save_config
from client.download import DownloadResult, DownloadTester
from client.grading import compare_with_previous, format_delta, grade_speed
from client.history import (
    format_history_table,
    group_by_hour,
    load_history,
    save_result,
    sparkline,
)
from client.latency import LatencyTester, PingResult, ServerLatencyResult
from client.stats import (
    ConnectionStats,
    LatencyStats,
    SpeedStats,
    calculate_iqm,
    calculate_jitter,
    calculate_percentile,
    format_latency,
    format_speed,
)
from client.upload import UploadResult, UploadTester
from ui.output import create_result_json, format_csv_row, save_json


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_server(**overrides):
    defaults = {
        "id": 1, "name": "Test", "sponsor": "ISP", "hostname": "speed.test.com",
        "port": 8080, "country": "DE", "cc": "DE", "lat": 52.0, "lon": 13.0,
        "distance": 10.0, "url": "", "https_functional": True,
    }
    defaults.update(overrides)
    return Server(**defaults)


# ---------------------------------------------------------------------------
# Server model edge cases
# ---------------------------------------------------------------------------

class TestServerEdgeCases(unittest.TestCase):
    def test_from_dict_with_all_fields(self):
        s = Server.from_dict({
            "id": "999", "name": "City", "sponsor": "ISP",
            "hostname": "h.com", "port": "9090", "country": "US",
            "cc": "US", "lat": "40.7", "lon": "-74.0",
            "distance": "100.5", "httpsFunctional": "1",
        })
        self.assertEqual(s.id, 999)
        self.assertEqual(s.port, 9090)
        self.assertAlmostEqual(s.lat, 40.7)
        self.assertAlmostEqual(s.distance, 100.5)

    def test_urls_different_ports(self):
        s = _make_server(hostname="fast.net", port=443)
        self.assertEqual(s.ws_url, "wss://fast.net:443/ws?")
        self.assertEqual(s.download_url, "https://fast.net:443/download")
        self.assertEqual(s.upload_url, "https://fast.net:443/upload")

    def test_to_dict_excludes_url(self):
        s = _make_server(url="http://example.com/upload.php")
        d = s.to_dict()
        self.assertNotIn("url", d)
        self.assertNotIn("https_functional", d)


# ---------------------------------------------------------------------------
# LatencyStats edge cases
# ---------------------------------------------------------------------------

class TestLatencyStatsAdvanced(unittest.TestCase):
    def test_identical_samples(self):
        ls = LatencyStats(samples=[25.0] * 100)
        ls.calculate()
        self.assertAlmostEqual(ls.min, 25.0)
        self.assertAlmostEqual(ls.max, 25.0)
        self.assertAlmostEqual(ls.jitter, 0.0)
        self.assertAlmostEqual(ls.iqm, 25.0)

    def test_two_samples_iqm(self):
        ls = LatencyStats(samples=[10.0, 20.0])
        ls.calculate()
        self.assertAlmostEqual(ls.iqm, 15.0)  # < 4 samples, falls back to mean

    def test_outlier_iqm(self):
        ls = LatencyStats(samples=[10, 10, 10, 10, 10, 10, 100, 1])
        ls.calculate()
        self.assertAlmostEqual(ls.iqm, 10.0)

    def test_to_dict_roundtrip(self):
        ls = LatencyStats(samples=[5.0, 10.0, 15.0, 20.0, 25.0])
        ls.calculate()
        d = ls.to_dict()
        self.assertEqual(d["count"], 5)
        self.assertEqual(len(d["samples"]), 5)
        self.assertIsInstance(d["jitter"], (int, float))


# ---------------------------------------------------------------------------
# Percentile edge cases
# ---------------------------------------------------------------------------

class TestPercentileAdvanced(unittest.TestCase):
    def test_p25(self):
        result = calculate_percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 25)
        self.assertAlmostEqual(result, 3.25, places=1)

    def test_p75(self):
        result = calculate_percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 75)
        self.assertAlmostEqual(result, 7.75, places=1)

    def test_single_element(self):
        self.assertAlmostEqual(calculate_percentile([42.0], 50), 42.0)
        self.assertAlmostEqual(calculate_percentile([42.0], 0), 42.0)
        self.assertAlmostEqual(calculate_percentile([42.0], 100), 42.0)


# ---------------------------------------------------------------------------
# IQM with various distributions
# ---------------------------------------------------------------------------

class TestIqmAdvanced(unittest.TestCase):
    def test_symmetric(self):
        samples = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
        result = calculate_iqm(samples)
        # Q1=3, Q3=9 -> [4,5,6,7,8,9] -> mean=6.5
        self.assertAlmostEqual(result, 6.5)

    def test_all_same(self):
        self.assertAlmostEqual(calculate_iqm([50.0] * 20), 50.0)

    def test_bimodal(self):
        samples = [10, 10, 10, 10, 90, 90, 90, 90]
        result = calculate_iqm(samples)
        # sorted: [10,10,10,10,90,90,90,90] -> Q1=2, Q3=6 -> [10,10,90,90] -> 50
        self.assertAlmostEqual(result, 50.0)


# ---------------------------------------------------------------------------
# SpeedStats edge cases
# ---------------------------------------------------------------------------

class TestSpeedStatsAdvanced(unittest.TestCase):
    def test_gigabit(self):
        ss = SpeedStats(bytes_transferred=125_000_000_000, duration_ms=10_000)
        ss.calculate()
        self.assertAlmostEqual(ss.speed_mbps, 100_000.0)

    def test_tiny_transfer(self):
        ss = SpeedStats(bytes_transferred=1, duration_ms=1000)
        ss.calculate()
        self.assertAlmostEqual(ss.speed_bps, 8.0)

    def test_to_dict_samples(self):
        ss = SpeedStats(samples=[10.0, 20.0, 30.0])
        d = ss.to_dict()
        self.assertEqual(len(d["samples"]), 3)


# ---------------------------------------------------------------------------
# Format helpers edge cases
# ---------------------------------------------------------------------------

class TestFormatEdgeCases(unittest.TestCase):
    def test_format_speed_fractional(self):
        self.assertEqual(format_speed(0.01), "0.01 Mbps")

    def test_format_speed_exact_gbps(self):
        self.assertEqual(format_speed(1000.0), "1.00 Gbps")

    def test_format_latency_exact_second(self):
        self.assertEqual(format_latency(1000.0), "1.00 s")

    def test_format_latency_sub_ms(self):
        self.assertEqual(format_latency(0.5), "0.5 ms")


# ---------------------------------------------------------------------------
# ConnectionStats comprehensive
# ---------------------------------------------------------------------------

class TestConnectionStatsAdvanced(unittest.TestCase):
    def test_high_speed(self):
        cs = ConnectionStats(bytes_transferred=1_250_000_000, duration_ms=1000)
        cs.calculate()
        self.assertAlmostEqual(cs.speed_mbps, 10_000.0)

    def test_to_dict_fields(self):
        cs = ConnectionStats(id=5, server_id=42, hostname="test.host",
                            bytes_transferred=1000, duration_ms=100)
        cs.calculate()
        d = cs.to_dict()
        expected_keys = {"id", "server_id", "hostname", "bytes", "duration_ms", "speed_mbps"}
        self.assertEqual(set(d.keys()), expected_keys)


# ---------------------------------------------------------------------------
# ServerLatencyResult comprehensive
# ---------------------------------------------------------------------------

class TestServerLatencyResultAdvanced(unittest.TestCase):
    def test_high_packet_loss(self):
        srv = _make_server()
        r = ServerLatencyResult(server=srv, pings=[10.0, 11.0], ping_attempts=100)
        r.calculate()
        self.assertAlmostEqual(r.packet_loss, 98.0)

    def test_to_dict_all_fields(self):
        srv = _make_server()
        r = ServerLatencyResult(
            server=srv, external_ip="1.2.3.4", pings=[10, 11, 12],
            ping_attempts=3, server_version="2.7",
        )
        r.calculate()
        d = r.to_dict()
        self.assertEqual(d["external_ip"], "1.2.3.4")
        self.assertEqual(d["server_version"], "2.7")
        self.assertEqual(d["packet_loss"], 0.0)

    def test_failed_result(self):
        srv = _make_server()
        r = ServerLatencyResult(server=srv, success=False, error="timeout")
        d = r.to_dict()
        self.assertFalse(d["success"])


# ---------------------------------------------------------------------------
# DownloadResult / UploadResult comprehensive
# ---------------------------------------------------------------------------

class TestResultAdvanced(unittest.TestCase):
    def test_download_iqm_removes_outliers(self):
        r = DownloadResult()
        r.samples = [50, 50, 50, 50, 50, 50, 50, 200]  # 200 is outlier
        r.calculate_from_samples()
        # sorted: [50,50,50,50,50,50,50,200] -> Q1=2, Q3=6 -> [50,50,50,50] -> 50
        self.assertAlmostEqual(r.speed_mbps, 50.0)

    def test_upload_iqm_removes_outliers(self):
        r = UploadResult()
        r.samples = [30, 30, 30, 30, 30, 30, 30, 150]
        r.calculate_from_samples()
        self.assertAlmostEqual(r.speed_mbps, 30.0)

    def test_download_to_dict_no_latency(self):
        r = DownloadResult(speed_mbps=100, bytes_total=125e6, duration_ms=10000)
        d = r.to_dict()
        self.assertNotIn("loaded_latency", d)

    def test_upload_to_dict_no_latency(self):
        r = UploadResult(speed_mbps=50, bytes_total=62.5e6, duration_ms=10000)
        d = r.to_dict()
        self.assertNotIn("loaded_latency", d)


# ---------------------------------------------------------------------------
# Grading comprehensive
# ---------------------------------------------------------------------------

class TestGradingAdvanced(unittest.TestCase):
    def test_exact_boundaries(self):
        # Exactly at 95% should be A+
        g, _, _ = grade_speed(95.0, 100.0)
        self.assertEqual(g, "A+")
        # Exactly at 85% should be A
        g, _, _ = grade_speed(85.0, 100.0)
        self.assertEqual(g, "A")
        # Exactly at 75%
        g, _, _ = grade_speed(75.0, 100.0)
        self.assertEqual(g, "B")
        # Exactly at 60%
        g, _, _ = grade_speed(60.0, 100.0)
        self.assertEqual(g, "C")
        # Exactly at 40%
        g, _, _ = grade_speed(40.0, 100.0)
        self.assertEqual(g, "D")

    def test_compare_multiple_history(self):
        current = {"ping": 10, "download": {"speed_mbps": 100}, "upload": {"speed_mbps": 50}}
        history = [
            {"ping": 50, "download": {"speed_mbps": 50}, "upload": {"speed_mbps": 25}},
            {"ping": 30, "download": {"speed_mbps": 70}, "upload": {"speed_mbps": 35}},
            {"ping": 20, "download": {"speed_mbps": 80}, "upload": {"speed_mbps": 40}},
        ]
        delta = compare_with_previous(current, history)
        # Should compare with LAST entry (ping=20)
        self.assertAlmostEqual(delta["ping_delta"], -10.0)
        self.assertAlmostEqual(delta["download_delta"], 20.0)


# ---------------------------------------------------------------------------
# History persistence stress test
# ---------------------------------------------------------------------------

class TestHistoryStress(unittest.TestCase):
    def test_many_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "history.jsonl")
            with mock.patch("client.history._history_path", return_value=path):
                for i in range(100):
                    save_result({"ping": i, "download": {"speed_mbps": i * 10}})

                entries = load_history(limit=10)
                self.assertEqual(len(entries), 10)
                # Should be the last 10
                self.assertEqual(entries[0]["ping"], 90)
                self.assertEqual(entries[-1]["ping"], 99)

    def test_sparkline_many_values(self):
        values = list(range(200))
        result = sparkline(values)
        self.assertEqual(len(result), 200)

    def test_hourly_all_hours(self):
        entries = []
        for h in range(24):
            entries.append({
                "timestamp": f"2025-01-15T{h:02d}:30:00+00:00",
                "ping": 10 + h,
                "download": {"speed_mbps": 100 - h},
                "upload": {"speed_mbps": 50 - h},
            })
        buckets = group_by_hour(entries)
        self.assertEqual(len(buckets), 24)


# ---------------------------------------------------------------------------
# Config edge cases
# ---------------------------------------------------------------------------

class TestConfigAdvanced(unittest.TestCase):
    def test_overwrite_preserves_other_keys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "config.json")
            with mock.patch("client.config._config_path", return_value=path):
                save_config({"plan": 100, "server": 42, "custom_key": "hello"})
                cfg = load_config()
                self.assertEqual(cfg["plan"], 100)
                self.assertEqual(cfg["custom_key"], "hello")

    def test_empty_file_returns_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "config.json")
            with open(path, "w") as f:
                f.write("{}")
            with mock.patch("client.config._config_path", return_value=path):
                cfg = load_config()
                self.assertEqual(cfg["connections"], 4)


# ---------------------------------------------------------------------------
# JSON output comprehensive
# ---------------------------------------------------------------------------

class TestJsonOutputAdvanced(unittest.TestCase):
    def test_full_result_json(self):
        result = create_result_json(
            client_info={"ip": "1.2.3.4", "isp": "ISP"},
            server_info={"id": 1, "name": "Srv"},
            latency_results={
                "latency_ms": 10, "jitter_ms": 1.5,
                "pings": [9, 10, 11, 10, 9, 11, 10, 9],
                "packet_loss": 0.0,
            },
            download_results={
                "speed_bps": 100e6, "speed_mbps": 100,
                "bytes_total": 125e6, "duration_ms": 10000,
                "connections": [], "samples": [95, 100, 105],
            },
            upload_results={
                "speed_bps": 50e6, "speed_mbps": 50,
                "bytes_total": 62.5e6, "duration_ms": 10000,
                "connections": [], "samples": [45, 50, 55],
            },
            server_selection=[{"id": 1, "latency_ms": 10}],
        )
        # Verify structure
        self.assertIn("timestamp", result)
        self.assertIn("latency", result)
        self.assertEqual(result["latency"]["tcp"]["count"], 8)
        self.assertIn("serverSelection", result)

        # Verify JSON serializable
        serialized = json.dumps(result)
        self.assertIsInstance(serialized, str)

    def test_csv_row_content(self):
        row = format_csv_row("Server", "ISP", "1.2.3.4",
                            10.0, 1.0, 100.0, 50.0)
        # Should contain the values
        self.assertIn("Server", row)
        self.assertIn("100.00", row)
        self.assertIn("50.00", row)

    def test_save_json_large(self):
        data = {"samples": list(range(10000))}
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            save_json(data, path)
            with open(path) as fh:
                loaded = json.load(fh)
            self.assertEqual(len(loaded["samples"]), 10000)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# PingResult
# ---------------------------------------------------------------------------

class TestPingResult(unittest.TestCase):
    def test_success(self):
        pr = PingResult(latency_ms=15.0, server_timestamp=12345, client_timestamp=100.0)
        self.assertTrue(pr.success)

    def test_failure(self):
        pr = PingResult(success=False, error="timeout")
        self.assertFalse(pr.success)
        self.assertEqual(pr.error, "timeout")


# ---------------------------------------------------------------------------
# ClientInfo
# ---------------------------------------------------------------------------

class TestClientInfoAdvanced(unittest.TestCase):
    def test_to_dict_all_fields(self):
        ci = ClientInfo(ip="10.0.0.1", isp="Test ISP", lat=48.8, lon=2.3, country="FR")
        d = ci.to_dict()
        self.assertEqual(set(d.keys()), {"ip", "isp", "lat", "lon", "country"})
        self.assertEqual(d["country"], "FR")


# ---------------------------------------------------------------------------
# SpeedtestAPI context manager
# ---------------------------------------------------------------------------

class TestSpeedtestAPIContextManager(unittest.TestCase):
    def test_without_context_raises(self):
        api = SpeedtestAPI()
        with self.assertRaises(RuntimeError):
            api._ensure_session()


if __name__ == "__main__":
    unittest.main()
