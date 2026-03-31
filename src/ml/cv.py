"""Simple purged time-series split helper.

This provides a compact PurgedTimeSeriesSplit that produces train/test
index pairs for sequential data while removing a purge window around each
test fold to avoid leakage. It also supports a small embargo fraction.

This is intentionally lightweight and not a drop-in replacement for
finance-specific libraries, but is suitable for unit tests and simple
experiments.
"""
from __future__ import annotations

from typing import Iterator, List, Tuple


class PurgedTimeSeriesSplit:
    def __init__(self, n_splits: int = 5, purge: int = 0, embargo: float = 0.0):
        if n_splits < 1:
            raise ValueError('n_splits must be >= 1')
        if purge < 0:
            raise ValueError('purge must be >= 0')
        if not (0.0 <= embargo < 1.0):
            raise ValueError('embargo must be in [0.0, 1.0)')

        self.n_splits = int(n_splits)
        self.purge = int(purge)
        self.embargo = float(embargo)

    def split(self, n_samples: int) -> Iterator[Tuple[List[int], List[int]]]:
        """Yield (train_idx, test_idx) pairs for data with `n_samples` rows.

        The implementation partitions the sequence into `n_splits` contiguous
        test segments of (approximately) equal size and purges `self.purge`
        indices on both sides of each test segment from the training set.
        An optional embargo (fraction of dataset length) is applied to the
        right-hand side of each test segment.
        """
        n = int(n_samples)
        if n <= 0:
            raise ValueError('n_samples must be > 0')

        # compute test size (floor division, last fold may be slightly larger)
        base_test_size = max(1, n // self.n_splits)

        for k in range(self.n_splits):
            start = k * base_test_size
            end = start + base_test_size
            if k == self.n_splits - 1:
                end = n

            # purge around test window (exclude both sides)
            left_purge = max(0, start - self.purge)
            right_purge = min(n, end + self.purge)

            # embargo sized in absolute samples (applied to the right side)
            embargo_size = int(n * self.embargo)
            right_embargo = min(n, end + embargo_size)

            # combine purge and embargo exclusions: exclude indices in [left_purge, max(right_purge, right_embargo))
            exclude_start = left_purge
            exclude_end = max(right_purge, right_embargo)

            # determine training indices: outside [exclude_start, exclude_end)
            train_idx = [i for i in range(n) if i < exclude_start or i >= exclude_end]
            test_idx = [i for i in range(start, end)]

            yield train_idx, test_idx
