import unittest
import os
import sys

# ensure src package is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.ml.feature_store import compute_latest_features


class FeatureStoreTests(unittest.TestCase):
    def test_basic_features(self):
        prices = [100.0 + i for i in range(20)]
        feats = compute_latest_features(prices)
        self.assertIsInstance(feats, dict)
        self.assertAlmostEqual(feats['last_price'], prices[-1])
        self.assertIn('rsi_14', feats)
        self.assertIn('macd', feats)
        self.assertIn('bb_upper', feats)

    def test_avg_vol(self):
        prices = [10.0 + i * 0.1 for i in range(10)]
        volumes = [1000 for _ in prices]
        feats = compute_latest_features(prices, volumes=volumes)
        self.assertEqual(feats['avg_vol_5'], 1000.0)


if __name__ == '__main__':
    unittest.main()
