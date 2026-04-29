import os
import sys
import unittest

# ensure src package is importable when tests run directly
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class IdxRulesTests(unittest.TestCase):
    def test_regular_tier_100(self):
        from src.execution.idx_rules import calculate_idx_limits

        limits = calculate_idx_limits(100)
        self.assertEqual(limits["tick"], 1)
        self.assertEqual(limits["ara"], 135)
        self.assertEqual(limits["arb"], 65)

    def test_high_price_tick_25(self):
        from src.execution.idx_rules import calculate_idx_limits

        limits = calculate_idx_limits(10000)
        self.assertEqual(limits["tick"], 25)
        self.assertEqual(limits["ara"], 12000)
        self.assertEqual(limits["arb"], 8000)

    def test_regular_low_price_forced_to_50(self):
        # regular board should enforce an ARB floor of Rp50 even for very low prices
        from src.execution.idx_rules import calculate_idx_limits

        limits = calculate_idx_limits(1)
        self.assertEqual(limits["arb"], 50)

    def test_fca_low_price_allows_1(self):
        # FCA allows ARB floor down to Rp1
        from src.execution.idx_rules import calculate_idx_limits

        limits = calculate_idx_limits(1, is_fca=True)
        self.assertEqual(limits["arb"], 1)

    def test_tier_crossing_uses_result_price_ticks(self):
        # previous close 490 sits on tick=2 tier, but ARA crosses into tick=5 tier.
        from src.execution.idx_rules import calculate_idx_limits

        limits = calculate_idx_limits(490)

        # 490 * 1.25 = 612.5 -> round down with tick 5 => 610
        self.assertEqual(limits["ara"], 610)
        # 490 * 0.75 = 367.5 -> round up with tick 2 => 368
        self.assertEqual(limits["arb"], 368)
        self.assertEqual(limits["araTick"], 5)
        self.assertEqual(limits["arbTick"], 2)


if __name__ == "__main__":
    unittest.main()
