import os
import sys
import time
import unittest
from unittest.mock import Mock

# ensure src package is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class SchedulerTests(unittest.TestCase):
    def test_scheduler_invokes_pipeline_periodically(self):
        mock_pipeline = Mock()
        mock_pipeline.run = Mock()

        from src.pipeline.scheduler import PipelineScheduler

        sched = PipelineScheduler(mock_pipeline, symbols=['AAA'], interval_seconds=0.05)
        started = sched.start()
        self.assertTrue(started)
        # allow a few intervals to pass
        time.sleep(0.18)
        sched.stop()

        # should have been called at least once
        self.assertGreaterEqual(mock_pipeline.run.call_count, 1)

    def test_run_once(self):
        mock_pipeline = Mock()
        mock_pipeline.run = Mock()
        from src.pipeline.scheduler import PipelineScheduler

        sched = PipelineScheduler(mock_pipeline, symbols=['AAA'], interval_seconds=1.0)
        sched.run_once()
        mock_pipeline.run.assert_called_once()


if __name__ == '__main__':
    unittest.main()
