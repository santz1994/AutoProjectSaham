import unittest

from fastapi.testclient import TestClient

from src.api import server


class APIServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not getattr(server, "FASTAPI_AVAILABLE", False):
            raise unittest.SkipTest("FastAPI not available")
        cls.client = TestClient(server.app)

    def test_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("status"), "ok")

    def test_etl_runs(self):
        r = self.client.get("/etl_runs")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("runs", data)
        self.assertIsInstance(data["runs"], list)

    def test_metrics(self):
        r = self.client.get("/metrics")
        # If prometheus_client unavailable, server returns 501
        self.assertIn(r.status_code, (200, 501))

    def test_charts_metadata_rejects_non_forex_crypto_symbol(self):
        r = self.client.get("/api/charts/metadata/BBCA.JK")
        self.assertEqual(r.status_code, 400)

    def test_charts_candles_rejects_non_forex_crypto_symbol(self):
        r = self.client.get("/api/charts/candles/BBCA.JK")
        self.assertEqual(r.status_code, 400)

    def test_charts_trading_status_rejects_invalid_market(self):
        r = self.client.get("/api/charts/trading-status?market=stock")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
