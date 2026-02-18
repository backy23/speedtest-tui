"""Unit tests for client.api -- data models and serialisation."""

import unittest

from client.api import ClientInfo, Server


class TestServer(unittest.TestCase):
    SAMPLE = {
        "id": 12345,
        "name": "Test City",
        "sponsor": "Test ISP",
        "hostname": "speed.test.com",
        "host": "speed.test.com:8080",
        "port": 8080,
        "country": "Germany",
        "cc": "DE",
        "lat": 52.52,
        "lon": 13.405,
        "distance": 42.5,
        "url": "http://speed.test.com/upload.php",
        "httpsFunctional": True,
    }

    def test_from_dict(self):
        s = Server.from_dict(self.SAMPLE)
        self.assertEqual(s.id, 12345)
        self.assertEqual(s.name, "Test City")
        self.assertEqual(s.hostname, "speed.test.com")
        self.assertEqual(s.port, 8080)
        self.assertAlmostEqual(s.distance, 42.5)

    def test_from_dict_defaults(self):
        s = Server.from_dict({})
        self.assertEqual(s.id, 0)
        self.assertEqual(s.name, "")
        self.assertEqual(s.port, 8080)
        self.assertTrue(s.https_functional)

    def test_ws_url(self):
        s = Server.from_dict(self.SAMPLE)
        self.assertEqual(s.ws_url, "wss://speed.test.com:8080/ws?")

    def test_download_url(self):
        s = Server.from_dict(self.SAMPLE)
        self.assertEqual(s.download_url, "https://speed.test.com:8080/download")

    def test_upload_url(self):
        s = Server.from_dict(self.SAMPLE)
        self.assertEqual(s.upload_url, "https://speed.test.com:8080/upload")

    def test_to_dict_roundtrip(self):
        s = Server.from_dict(self.SAMPLE)
        d = s.to_dict()
        self.assertEqual(d["id"], 12345)
        self.assertEqual(d["name"], "Test City")
        self.assertIn("distance", d)

    def test_hostname_fallback_from_host(self):
        data = {"host": "fallback.host.com:9090"}
        s = Server.from_dict(data)
        self.assertEqual(s.hostname, "fallback.host.com")


class TestClientInfo(unittest.TestCase):
    def test_to_dict(self):
        ci = ClientInfo(ip="1.2.3.4", isp="TestISP", lat=50.0, lon=10.0, country="DE")
        d = ci.to_dict()
        self.assertEqual(d["ip"], "1.2.3.4")
        self.assertEqual(d["isp"], "TestISP")
        self.assertEqual(d["country"], "DE")


if __name__ == "__main__":
    unittest.main()
