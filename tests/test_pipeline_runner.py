import os
import sys
import unittest
from unittest.mock import Mock, patch

# ensure src package is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class PipelineRunnerTests(unittest.TestCase):
    def test_run_invokes_etl_and_batch_fetch(self):
        # mock run_etl to avoid network calls
        with patch(
            "src.pipeline.etl.run_etl",
            return_value={"stocks": {}, "forex": {}, "news": {}},
        ) as mock_etl:
            mock_fetcher = Mock()
            mock_fetcher.fetch_symbols.return_value = [
                {"symbol": "AAA", "status": "ok"},
            ]

            from src.pipeline.runner import AutonomousPipeline

            runner = AutonomousPipeline(batch_fetcher=mock_fetcher)
            res = runner.run(["AAA"], fetch_prices=True)

            self.assertIn("etl", res)
            self.assertIn("prices", res)
            self.assertEqual(res["prices"][0]["symbol"], "AAA")
            mock_etl.assert_called_once()


if __name__ == "__main__":
    unittest.main()
