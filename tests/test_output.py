"""Unit tests for ui.output -- JSON creation and text formatting."""

import json
import os
import tempfile
import unittest

from ui.output import (
    create_result_json,
    format_csv_header,
    format_csv_row,
    format_text_result,
    save_json,
)


class TestCreateResultJson(unittest.TestCase):
    def _make(self, **overrides):
        defaults = dict(
            client_info={"ip": "1.2.3.4", "isp": "ISP"},
            server_info={"id": 1, "name": "Srv"},
            latency_results={"latency_ms": 10.0, "jitter_ms": 1.5, "pings": [9.0, 10.0, 11.0]},
            download_results={"speed_bps": 100e6, "speed_mbps": 100.0, "bytes_total": 125e6, "duration_ms": 10000},
            upload_results={"speed_bps": 50e6, "speed_mbps": 50.0, "bytes_total": 62.5e6, "duration_ms": 10000},
        )
        defaults.update(overrides)
        return create_result_json(**defaults)

    def test_basic_structure(self):
        r = self._make()
        self.assertIn("timestamp", r)
        self.assertIn("client", r)
        self.assertIn("download", r)
        self.assertIn("upload", r)
        self.assertIn("latency", r)

    def test_ping_stats(self):
        r = self._make()
        tcp = r["latency"]["tcp"]
        self.assertEqual(tcp["count"], 3)
        self.assertAlmostEqual(tcp["rtt"]["min"], 9.0)
        self.assertAlmostEqual(tcp["rtt"]["max"], 11.0)

    def test_empty_pings(self):
        r = self._make(latency_results={"pings": []})
        tcp = r["latency"]["tcp"]
        self.assertEqual(tcp["count"], 0)
        self.assertEqual(tcp["rtt"]["min"], 0)

    def test_server_selection(self):
        r = self._make(server_selection=[{"id": 1}])
        self.assertIn("serverSelection", r)

    def test_no_server_selection(self):
        r = self._make()
        self.assertNotIn("serverSelection", r)


class TestSaveJson(unittest.TestCase):
    def test_roundtrip(self):
        data = {"key": "value", "number": 42}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            save_json(data, path)
            with open(path) as fh:
                loaded = json.load(fh)
            self.assertEqual(loaded, data)
        finally:
            os.unlink(path)

    def test_atomic_no_partial(self):
        # If the directory doesn't exist, it should raise, not leave a temp file
        with self.assertRaises(IOError):
            save_json({"a": 1}, "/nonexistent/dir/file.json")


class TestFormatTextResult(unittest.TestCase):
    def test_contains_values(self):
        text = format_text_result(
            ping_ms=15.0, jitter_ms=2.0, download_mbps=100.0,
            upload_mbps=50.0, server_name="Test", isp="ISP", ip="1.2.3.4",
        )
        self.assertIn("15.0 ms", text)
        self.assertIn("100.00 Mbps", text)
        self.assertIn("50.00 Mbps", text)
        self.assertIn("Test", text)


class TestCsvHelpers(unittest.TestCase):
    def test_header(self):
        h = format_csv_header()
        self.assertIn("timestamp", h)
        self.assertIn("download_mbps", h)

    def test_row(self):
        row = format_csv_row("Srv", "ISP", "1.2.3.4", 10.0, 1.0, 100.0, 50.0)
        parts = row.split(",")
        self.assertEqual(len(parts), 8)


if __name__ == "__main__":
    unittest.main()
