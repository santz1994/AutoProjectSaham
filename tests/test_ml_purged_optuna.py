import os
import sys
import unittest

# ensure src package is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class PurgedCVTests(unittest.TestCase):
    def test_purged_splits_basic(self):
        n = 12
        from src.ml.cv import PurgedTimeSeriesSplit

        pts = PurgedTimeSeriesSplit(n_splits=3, purge=1, embargo=0.0)
        splits = list(pts.split(n))
        # expected three folds as contiguous blocks of size 4
        expected_tests = [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9, 10, 11]]
        self.assertEqual([t for (_, t) in splits], expected_tests)

        # expected training indices with purge=1
        self.assertEqual(splits[0][0], list(range(5, 12)))
        self.assertEqual(splits[1][0], list(range(0, 3)) + list(range(9, 12)))
        self.assertEqual(splits[2][0], list(range(0, 7)))


class OptunaWrapperTests(unittest.TestCase):
    def test_optimize_integer_param_fallback(self):
        # objective with maximum at x=3 (integer)
        def obj(x: int):
            return -((x - 3) ** 2)

        from src.ml.optuna_wrapper import optimize

        params, score = optimize(
            obj,
            {"x": (0, 6, "int")},
            n_trials=7,
            random_state=123,
        )
        # best possible score is 0 at x=3
        self.assertEqual(params.get("x"), 3)
        self.assertAlmostEqual(score, 0.0, places=6)


if __name__ == "__main__":
    unittest.main()
