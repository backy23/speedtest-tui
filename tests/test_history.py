"""Unit tests for client.history -- persistence and display helpers."""

import json
import os
import tempfile
import unittest
from unittest import mock

from client.history import (
    format_history_table,
    load_history,
    save_result,
    sparkline,
)


class TestSparkline(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(sparkline([]), "")

    def test_constant(self):
        result = sparkline([5.0, 5.0, 5.0])
        self.assertEqual(len(result), 3)

    def test_ascending(self):
        result = sparkline([1, 2, 3, 4, 5, 6, 7, 8])
        self.assertTrue(len(result) == 8)
        # First char should be lowest bar, last should be highest
        self.assertEqual(result[0], "\u2581")  # ▁
        self.assertEqual(result[-1], "\u2588")  # █

    def test_single(self):
        result = sparkline([42.0])
        self.assertEqual(len(result), 1)


class TestFormatHistoryTable(unittest.TestCase):
    def test_basic(self):
        entries = [
            {
                "timestamp": "2025-01-15T10:30:00+00:00",
                "server": {"name": "Berlin", "sponsor": "ISP"},
                "ping": 15.0,
                "jitter": 2.0,
                "download": {"speed_mbps": 100.0},
                "upload": {"speed_mbps": 50.0},
            }
        ]
        rows = format_history_table(entries)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["server"], "Berlin (ISP)")
        self.assertAlmostEqual(rows[0]["download"], 100.0)

    def test_missing_fields(self):
        entries = [{"timestamp": "2025-01-15"}]
        rows = format_history_table(entries)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ping"], 0)

    def test_empty(self):
        self.assertEqual(format_history_table([]), [])


class TestSaveAndLoad(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "history.jsonl")

            with mock.patch("client.history._history_path", return_value=path):
                save_result({"ping": 10, "download": {"speed_mbps": 100}})
                save_result({"ping": 12, "download": {"speed_mbps": 95}})

                entries = load_history()
                self.assertEqual(len(entries), 2)
                self.assertEqual(entries[0]["ping"], 10)
                self.assertEqual(entries[1]["ping"], 12)

    def test_load_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "nonexistent.jsonl")
            with mock.patch("client.history._history_path", return_value=path):
                self.assertEqual(load_history(), [])

    def test_corrupt_lines_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "history.jsonl")
            with open(path, "w") as f:
                f.write('{"ping": 10}\n')
                f.write("NOT JSON\n")
                f.write('{"ping": 20}\n')

            with mock.patch("client.history._history_path", return_value=path):
                entries = load_history()
                self.assertEqual(len(entries), 2)


class TestPacketLoss(unittest.TestCase):
    """Test that ServerLatencyResult computes packet_loss correctly."""

    def test_no_loss(self):
        from client.latency import ServerLatencyResult
        from client.api import Server

        srv = Server.from_dict({"id": 1, "name": "Test"})
        r = ServerLatencyResult(server=srv, pings=[10.0, 11.0, 12.0], ping_attempts=3)
        r.calculate()
        self.assertAlmostEqual(r.packet_loss, 0.0)

    def test_with_loss(self):
        from client.latency import ServerLatencyResult
        from client.api import Server

        srv = Server.from_dict({"id": 1, "name": "Test"})
        r = ServerLatencyResult(server=srv, pings=[10.0, 11.0], ping_attempts=5)
        r.calculate()
        self.assertAlmostEqual(r.packet_loss, 60.0)

    def test_zero_attempts(self):
        from client.latency import ServerLatencyResult
        from client.api import Server

        srv = Server.from_dict({"id": 1, "name": "Test"})
        r = ServerLatencyResult(server=srv, pings=[], ping_attempts=0)
        r.calculate()
        self.assertAlmostEqual(r.packet_loss, 0.0)


if __name__ == "__main__":
    unittest.main()
