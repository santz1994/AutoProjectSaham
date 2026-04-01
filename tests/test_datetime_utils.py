import unittest
import datetime

from src.utils.datetime_utils import fromtimestamp_utc, to_local


class DateTimeUtilsTests(unittest.TestCase):
    def test_fromtimestamp_utc_returns_utc(self):
        ts = 1774858442
        dt = fromtimestamp_utc(ts)
        self.assertIsNotNone(dt.tzinfo)
        self.assertEqual(dt.tzinfo, datetime.timezone.utc)
        # roundtrip
        self.assertEqual(int(dt.timestamp()), ts)

    def test_to_local_handles_naive_and_aware(self):
        ts = 1600000000
        # construct an aware UTC datetime and drop tzinfo to simulate a naive UTC timestamp
        aware = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
        naive = aware.replace(tzinfo=None)
        local = to_local(naive)
        self.assertIsNotNone(local.tzinfo)


if __name__ == "__main__":
    unittest.main()
