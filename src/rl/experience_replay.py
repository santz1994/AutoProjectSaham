"""Prioritized Experience Replay Buffer for Continuous RL Training.

Implements PER (Prioritized Experience Replay) with:
- Proportional prioritization using TD-error as priority signal
- Importance sampling weights to correct bias
- Segment-based sampling for efficient batch creation
- Market regime-aware priority boosting (recent regime data weighted higher)
- Thread-safe operations for concurrent training + inference
- Persistence: save/load buffer state to disk (pickle)

References:
    Schaul et al. (2015) - Prioritized Experience Replay
    Hessel et al. (2018) - Rainbow DQN (PER component)

Part of Phase D: Continuous Training Pipeline.
"""

from __future__ import annotations

import logging
import os
import pickle
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Experience:
    """Single transition tuple stored in the replay buffer."""
    state: np.ndarray
    action: np.ndarray
    reward: float
    next_state: np.ndarray
    done: bool
    info: Dict[str, Any] = field(default_factory=dict)
    # Metadata for regime-aware prioritization
    regime: str = "unknown"
    timestamp: float = field(default_factory=time.time)
    symbol: str = ""
    td_error: float = 0.0


class SumTree:
    """Binary sum tree for efficient proportional priority sampling.

    Stores priorities in a binary tree structure enabling O(log n)
    sampling and O(log n) priority updates.
    """

    def __init__(self, capacity: int):
        self.capacity = capacity
        self.tree = np.zeros(2 * capacity - 1, dtype=np.float64)
        self.data_pointer = 0
        self.size = 0

    def _propagate(self, idx: int, change: float):
        """Propagate priority change up the tree."""
        parent = (idx - 1) // 2
        self.tree[parent] += change
        if parent != 0:
            self._propagate(parent, change)

    def _retrieve(self, idx: int, s: float) -> int:
        """Find leaf index for cumulative sum s."""
        left = 2 * idx + 1
        right = left + 1
        if left >= len(self.tree):
            return idx
        if s <= self.tree[left]:
            return self._retrieve(left, s)
        else:
            return self._retrieve(right, s - self.tree[left])

    @property
    def total(self) -> float:
        """Total sum of all priorities."""
        return self.tree[0]

    def add(self, priority: float):
        """Add a new priority to the tree."""
        idx = self.data_pointer + self.capacity - 1
        self.update(idx, priority)
        self.data_pointer = (self.data_pointer + 1) % self.capacity
        self.size = min(self.size + 1, self.capacity)

    def update(self, idx: int, priority: float):
        """Update priority at tree index."""
        change = priority - self.tree[idx]
        self.tree[idx] = priority
        self._propagate(idx, change)

    def get(self, s: float) -> Tuple[int, float]:
        """Get leaf index and priority for cumulative sum s."""
        idx = self._retrieve(0, s)
        data_idx = idx - self.capacity + 1
        return idx, self.tree[idx], data_idx

    def min(self) -> float:
        """Minimum priority among all leaves (non-zero)."""
        leaves = self.tree[self.capacity - 1: self.capacity - 1 + self.size]
        if len(leaves) == 0:
            return 0.0
        non_zero = leaves[leaves > 0]
        return float(np.min(non_zero)) if len(non_zero) > 0 else 0.0


class PrioritizedReplayBuffer:
    """Prioritized Experience Replay Buffer.

    Stores transitions with priorities proportional to their TD-error.
    Samples transitions with higher TD-error more frequently.
    Applies importance sampling (IS) weights to correct the bias introduced
    by non-uniform sampling.

    Features:
    - Proportional prioritization (p^alpha sampling)
    - Importance sampling correction (IS weights: (1/(N*P))^beta)
    - Regime-aware priority boosting: recent regime transitions get 1.2x boost
    - Thread-safe for concurrent access
    - Disk persistence (save/load via pickle)
    """

    def __init__(
        self,
        capacity: int = 100_000,
        alpha: float = 0.6,
        beta_start: float = 0.4,
        beta_frames: int = 100_000,
        epsilon: float = 1e-6,
        regime_boost_factor: float = 1.2,
        regime_boost_window_hours: float = 24.0,
        device: str = "cpu",
    ):
        """
        Args:
            capacity: Maximum number of transitions to store.
            alpha: Priority exponent. alpha=0 is uniform, alpha=1 is full PER.
            beta_start: Initial importance sampling exponent.
            beta_frames: Number of frames to anneal beta from beta_start to 1.0.
            epsilon: Small constant added to priorities to ensure non-zero probability.
            regime_boost_factor: Priority multiplier for recent regime transitions.
            regime_boost_window_hours: Window for regime boost (hours).
            device: Device for tensor operations (currently unused, future-proof).
        """
        self.capacity = capacity
        self.alpha = alpha
        self.beta_start = beta_start
        self.beta_frames = beta_frames
        self.epsilon = epsilon
        self.regime_boost_factor = regime_boost_factor
        self.regime_boost_window_hours = regime_boost_window_hours
        self.device = device

        self._tree = SumTree(capacity)
        self._data: List[Optional[Experience]] = [None] * capacity
        self._position = 0
        self._size = 0
        self._frame = 0

        # Stats
        self._total_added = 0
        self._total_sampled = 0
        self._max_priority = 1.0

        # Thread safety
        self._lock = threading.RLock()

        logger.info(
            "PrioritizedReplayBuffer initialized: capacity=%d, alpha=%.2f, "
            "beta_start=%.2f, regime_boost=%.1fx",
            capacity, alpha, beta_start, regime_boost_factor,
        )

    @property
    def size(self) -> int:
        """Current number of stored transitions."""
        return self._size

    @property
    def beta(self) -> float:
        """Current importance sampling exponent (annealed)."""
        progress = min(self._frame / max(self.beta_frames, 1), 1.0)
        return self.beta_start + progress * (1.0 - self.beta_start)

    def add(self, experience: Experience, td_error: Optional[float] = None):
        """Add a transition to the buffer with priority based on TD-error.

        Args:
            experience: The transition to store.
            td_error: TD-error for this transition. If None, uses max priority.
        """
        with self._lock:
            if td_error is not None:
                experience.td_error = abs(td_error)
            else:
                experience.td_error = self._max_priority

            priority = self._compute_priority(experience)

            self._data[self._position] = experience
            self._tree.add(priority)

            self._position = (self._position + 1) % self.capacity
            self._size = min(self._size + 1, self.capacity)
            self._total_added += 1

            # Track max priority for new experiences
            self._max_priority = max(self._max_priority, experience.td_error + self.epsilon)

    def add_batch(self, experiences: List[Experience], td_errors: Optional[List[float]] = None):
        """Add multiple transitions in bulk."""
        for i, exp in enumerate(experiences):
            td = td_errors[i] if td_errors is not None else None
            self.add(exp, td_error=td)

    def sample(self, batch_size: int) -> Tuple[List[Experience], np.ndarray, np.ndarray]:
        """Sample a batch of transitions with proportional prioritization.

        Returns:
            experiences: List of sampled transitions.
            indices: Tree indices of sampled transitions (for priority updates).
            is_weights: Importance sampling weights for bias correction.
        """
        with self._lock:
            if self._size < batch_size:
                raise ValueError(
                    f"Not enough samples: {self._size} < {batch_size}"
                )

            experiences = []
            indices = []
            priorities = []

            segment = self._tree.total / batch_size

            current_beta = self.beta
            self._frame += 1

            for i in range(batch_size):
                low = segment * i
                high = segment * (i + 1)
                s = np.random.uniform(low, high)

                tree_idx, priority, data_idx = self._tree.get(s)

                if self._data[data_idx] is None:
                    # Fallback: sample random valid index
                    data_idx = np.random.randint(0, self._size)
                    # Find tree index for this data
                    tree_idx = data_idx + self.capacity - 1
                    priority = self._tree.tree[tree_idx]
                    if priority == 0:
                        priority = self.epsilon

                experiences.append(self._data[data_idx])
                indices.append(tree_idx)
                priorities.append(priority)

            # Importance sampling weights
            priorities_arr = np.array(priorities, dtype=np.float64)
            sampling_probs = priorities_arr / max(self._tree.total, 1e-10)
            sampling_probs = np.clip(sampling_probs, 1e-10, None)

            is_weights = (self._size * sampling_probs) ** (-current_beta)
            is_weights /= max(is_weights.max(), 1e-10)  # Normalize

            self._total_sampled += batch_size

            return experiences, np.array(indices, dtype=np.int64), is_weights.astype(np.float32)

    def update_priorities(self, indices: np.ndarray, td_errors: np.ndarray):
        """Update priorities for sampled transitions based on new TD-errors.

        Args:
            indices: Tree indices returned from sample().
            td_errors: New TD-errors (absolute values) for each transition.
        """
        with self._lock:
            for idx, td_error in zip(indices, td_errors):
                td_error = abs(float(td_error))
                data_idx = idx - self.capacity + 1

                if 0 <= data_idx < len(self._data) and self._data[data_idx] is not None:
                    self._data[data_idx].td_error = td_error

                priority = (td_error + self.epsilon) ** self.alpha

                # Apply regime boost if transition is recent
                if self._data[data_idx] is not None:
                    exp = self._data[data_idx]
                    age_hours = (time.time() - exp.timestamp) / 3600.0
                    if age_hours < self.regime_boost_window_hours and exp.regime != "unknown":
                        priority *= self.regime_boost_factor

                self._tree.update(idx, priority)
                self._max_priority = max(self._max_priority, td_error)

    def _compute_priority(self, experience: Experience) -> float:
        """Compute priority for a transition."""
        base_priority = (experience.td_error + self.epsilon) ** self.alpha

        # Boost recent regime transitions
        age_hours = (time.time() - experience.timestamp) / 3600.0
        if age_hours < self.regime_boost_window_hours and experience.regime != "unknown":
            base_priority *= self.regime_boost_factor

        return base_priority

    def get_stats(self) -> Dict[str, Any]:
        """Return buffer statistics."""
        with self._lock:
            return {
                "size": self._size,
                "capacity": self.capacity,
                "total_added": self._total_added,
                "total_sampled": self._total_sampled,
                "alpha": self.alpha,
                "beta_current": self.beta,
                "max_priority": self._max_priority,
                "tree_total": float(self._tree.total),
                "utilization": self._size / max(self.capacity, 1),
            }

    def save(self, filepath: str):
        """Save buffer state to disk."""
        with self._lock:
            state = {
                "data": self._data,
                "position": self._position,
                "size": self._size,
                "frame": self._frame,
                "total_added": self._total_added,
                "total_sampled": self._total_sampled,
                "max_priority": self._max_priority,
                "tree": self._tree.tree.copy(),
                "tree_data_pointer": self._tree.data_pointer,
                "tree_size": self._tree.size,
            }
            os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
            with open(filepath, "wb") as f:
                pickle.dump(state, f)
            logger.info("PER buffer saved: %d experiences → %s", self._size, filepath)

    def load(self, filepath: str):
        """Load buffer state from disk."""
        with self._lock:
            if not os.path.exists(filepath):
                logger.warning("PER buffer file not found: %s", filepath)
                return
            with open(filepath, "rb") as f:
                state = pickle.load(f)
            self._data = state["data"]
            self._position = state["position"]
            self._size = state["size"]
            self._frame = state["frame"]
            self._total_added = state["total_added"]
            self._total_sampled = state["total_sampled"]
            self._max_priority = state["max_priority"]
            self._tree.tree = state["tree"]
            self._tree.data_pointer = state["tree_data_pointer"]
            self._tree.size = state["tree_size"]
            logger.info("PER buffer loaded: %d experiences from %s", self._size, filepath)

    def clear(self):
        """Clear the buffer."""
        with self._lock:
            self._tree = SumTree(self.capacity)
            self._data = [None] * self.capacity
            self._position = 0
            self._size = 0
            self._frame = 0
            self._total_added = 0
            self._total_sampled = 0
            self._max_priority = 1.0
            logger.info("PER buffer cleared")


class ConceptDriftDetector:
    """Detects concept drift in financial time-series by monitoring
    distribution shifts in reward signals and feature statistics.

    Uses Page-Hinkley test and rolling statistics comparison.
    """

    def __init__(
        self,
        window_size: int = 1000,
        threshold: float = 0.05,
        min_samples: int = 200,
    ):
        self.window_size = window_size
        self.threshold = threshold
        self.min_samples = min_samples

        self._rewards: List[float] = []
        self._drift_detected = False
        self._drift_count = 0
        self._last_drift_idx = 0

        # Page-Hinkley parameters
        self._cumulative_sum = 0.0
        self._min_cumulative = float("inf")
        self._mean_estimate = 0.0
        self._count = 0

    def update(self, reward: float) -> bool:
        """Update detector with new reward. Returns True if drift detected."""
        self._rewards.append(reward)
        self._count += 1

        # Update mean estimate
        if self._count == 1:
            self._mean_estimate = reward
        else:
            self._mean_estimate += (reward - self._mean_estimate) / self._count

        # Page-Hinkley test
        self._cumulative_sum += reward - self._mean_estimate
        self._min_cumulative = min(self._min_cumulative, self._cumulative_sum)

        ph_statistic = self._cumulative_sum - self._min_cumulative

        if self._count > self.min_samples and ph_statistic > self.threshold:
            self._drift_detected = True
            self._drift_count += 1
            self._last_drift_idx = self._count
            # Reset after drift detection
            self._cumulative_sum = 0.0
            self._min_cumulative = float("inf")
            self._mean_estimate = 0.0
            self._count = 0
            self._rewards.clear()
            logger.warning(
                "Concept drift detected! (count=%d)", self._drift_count
            )
            return True

        self._drift_detected = False
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Return drift detector statistics."""
        return {
            "total_updates": self._count + self._last_drift_idx,
            "drift_count": self._drift_count,
            "last_drift_at": self._last_drift_idx,
            "current_mean_estimate": self._mean_estimate,
            "cumulative_sum": self._cumulative_sum,
        }