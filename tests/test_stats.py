"""Unit tests for client.stats -- pure functions and dataclasses."""

import unittest

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


class TestCalculateJitter(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(calculate_jitter([]), 0.0)

    def test_single(self):
        self.assertEqual(calculate_jitter([10.0]), 0.0)

    def test_constant(self):
        self.assertAlmostEqual(calculate_jitter([5.0, 5.0, 5.0]), 0.0)

    def test_two_samples(self):
        self.assertAlmostEqual(calculate_jitter([10.0, 15.0]), 5.0)

    def test_varying(self):
        # |15-10| + |10-15| + |20-10| = 5 + 5 + 10 = 20 / 3 ≈ 6.667
        result = calculate_jitter([10.0, 15.0, 10.0, 20.0])
        self.assertAlmostEqual(result, 20.0 / 3, places=3)


class TestCalculateIqm(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(calculate_iqm([]), 0.0)

    def test_few_samples(self):
        self.assertAlmostEqual(calculate_iqm([1.0, 2.0, 3.0]), 2.0)

    def test_normal(self):
        # sorted: [1, 2, 3, 4, 5, 6, 7, 8]  Q1=2, Q3=6 -> middle=[3,4,5,6] -> mean=4.5
        result = calculate_iqm([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
        self.assertAlmostEqual(result, 4.5)

    def test_outlier_resistant(self):
        # With extreme outliers, IQM should ignore them
        samples = [10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 100.0, 0.5]
        result = calculate_iqm(samples)
        # sorted: [0.5, 10, 10, 10, 10, 10, 10, 100] -> Q1=2, Q3=6 -> [10,10,10,10] -> 10
        self.assertAlmostEqual(result, 10.0)


class TestCalculatePercentile(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(calculate_percentile([], 50), 0.0)

    def test_median_odd(self):
        self.assertAlmostEqual(calculate_percentile([1, 2, 3, 4, 5], 50), 3.0)

    def test_p0(self):
        self.assertAlmostEqual(calculate_percentile([10, 20, 30], 0), 10.0)

    def test_p100(self):
        self.assertAlmostEqual(calculate_percentile([10, 20, 30], 100), 30.0)


class TestFormatSpeed(unittest.TestCase):
    def test_mbps(self):
        self.assertEqual(format_speed(50.0), "50.00 Mbps")

    def test_gbps(self):
        self.assertEqual(format_speed(1500.0), "1.50 Gbps")

    def test_zero(self):
        self.assertEqual(format_speed(0.0), "0.00 Mbps")


class TestFormatLatency(unittest.TestCase):
    def test_ms(self):
        self.assertEqual(format_latency(25.3), "25.3 ms")

    def test_seconds(self):
        self.assertEqual(format_latency(1500.0), "1.50 s")


class TestLatencyStats(unittest.TestCase):
    def test_calculate(self):
        ls = LatencyStats(samples=[10.0, 20.0, 15.0, 25.0, 12.0])
        ls.calculate()
        self.assertEqual(ls.count, 5)
        self.assertAlmostEqual(ls.min, 10.0)
        self.assertAlmostEqual(ls.max, 25.0)
        self.assertAlmostEqual(ls.mean, 16.4)
        self.assertGreater(ls.jitter, 0)

    def test_empty(self):
        ls = LatencyStats()
        ls.calculate()
        self.assertEqual(ls.count, 0)

    def test_to_dict(self):
        ls = LatencyStats(samples=[5.0, 10.0])
        ls.calculate()
        d = ls.to_dict()
        self.assertIn("min", d)
        self.assertIn("jitter", d)
        self.assertEqual(d["count"], 2)


class TestSpeedStats(unittest.TestCase):
    def test_calculate(self):
        ss = SpeedStats(bytes_transferred=125_000_000, duration_ms=10_000)
        ss.calculate()
        # 125MB in 10s = 100 Mbps
        self.assertAlmostEqual(ss.speed_mbps, 100.0)

    def test_zero_duration(self):
        ss = SpeedStats(bytes_transferred=100, duration_ms=0)
        ss.calculate()
        self.assertEqual(ss.speed_mbps, 0.0)


class TestConnectionStats(unittest.TestCase):
    def test_calculate(self):
        cs = ConnectionStats(bytes_transferred=12_500_000, duration_ms=1000)
        cs.calculate()
        self.assertAlmostEqual(cs.speed_mbps, 100.0)

    def test_to_dict(self):
        cs = ConnectionStats(id=1, server_id=42, hostname="test.host")
        d = cs.to_dict()
        self.assertEqual(d["id"], 1)
        self.assertEqual(d["server_id"], 42)


if __name__ == "__main__":
    unittest.main()
