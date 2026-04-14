import os
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _FakeExchange:
    def __init__(self, candles, timeframe_seconds=300):
        self._candles = candles
        self.rateLimit = 0
        self._timeframe_seconds = timeframe_seconds

    def parse_timeframe(self, timeframe):
        if timeframe != "5m":
            raise ValueError("Unsupported timeframe in fake exchange")
        return self._timeframe_seconds

    def milliseconds(self):
        if not self._candles:
            return 0
        return int(self._candles[-1][0])

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=1000):
        _ = (symbol, timeframe)
        since = 0 if since is None else int(since)
        idx = 0
        for i, row in enumerate(self._candles):
            if int(row[0]) >= since:
                idx = i
                break
        return self._candles[idx : idx + int(limit)]


def _build_candles(count=3000, start_ms=1700000000000, step_ms=300000):
    output = []
    price = 100.0
    for i in range(count):
        ts = start_ms + (i * step_ms)
        open_price = price
        high_price = price + 0.5
        low_price = price - 0.5
        close_price = price + 0.1
        volume = 10.0 + i
        output.append([ts, open_price, high_price, low_price, close_price, volume])
        price += 0.01
    return output


class HFConnectorTests(unittest.TestCase):
    def test_fetch_historical_data_to_dataframe(self):
        from src.pipeline.data_connectors.hf_connector import (
            fetch_historical_data_with_exchange,
        )

        candles = _build_candles(count=3000)
        exchange = _FakeExchange(candles=candles)

        df = fetch_historical_data_with_exchange(
            exchange=exchange,
            symbol="BTC/USDT",
            timeframe="5m",
            candles=2500,
            batch_limit=500,
            since_ms=candles[0][0],
            strict=True,
            sleep_seconds=0,
        )

        self.assertEqual(len(df), 2500)
        self.assertIn("timestamp", df.columns)
        self.assertIn("datetime", df.columns)
        self.assertIn("open", df.columns)
        self.assertIn("close", df.columns)

        timestamps = df["timestamp"].tolist()
        diffs = [timestamps[i] - timestamps[i - 1] for i in range(1, len(timestamps))]
        self.assertTrue(all(d == 300000 for d in diffs))

    def test_strict_mode_raises_on_interval_gap(self):
        from src.pipeline.data_connectors.hf_connector import (
            fetch_historical_data_with_exchange,
        )

        candles = _build_candles(count=1200)
        # Remove one candle to create a gap.
        del candles[400]

        exchange = _FakeExchange(candles=candles)

        with self.assertRaises(RuntimeError):
            fetch_historical_data_with_exchange(
                exchange=exchange,
                symbol="BTC/USDT",
                timeframe="5m",
                candles=1000,
                batch_limit=250,
                since_ms=candles[0][0],
                strict=True,
                sleep_seconds=0,
            )


if __name__ == "__main__":
    unittest.main()
