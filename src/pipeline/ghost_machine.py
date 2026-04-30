"""
Ghost Machine — Autonomous 24/7 Execution Loop

The "Ghost Machine" is the core trading loop that:
1. Pulls live candle data from exchange
2. Computes features via FeatureStore
3. RL Model predicts action (BUY/SELL/HOLD + sizing)
4. Anomaly Guard evaluates fat-tail risk
5. MiMo Supervisor provides geopolitical veto
6. Execution Manager places orders via CCXT

This runs continuously as a background worker (Celery/cron/direct thread).

Architecture:
  ┌─────────────────────────────────────────────────────────────────┐
  │                    Ghost Machine Loop                           │
  │                                                                 │
  │  [Exchange] → [Feature Store] → [RL Agent] → [Anomaly Guard]   │
  │       ↑                                                      ↓  │
  │  [CCXT Live]                                          [Execute] │
  │       ↑                                                      ↓  │
  │  [Order Result]  ←  [MiMo Supervisor]  ←  [SentimentScheduler] │
  └─────────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TradingCycleResult:
    """Result of a single trading cycle."""
    symbol: str
    timestamp: str
    action_taken: str  # "BUY", "SELL", "HOLD", "BLOCKED"
    target_fraction: float
    adjusted_fraction: float
    guard_decision: str
    anomaly_score: float
    sentiment_score: float
    price: float
    features_shape: tuple
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "action_taken": self.action_taken,
            "target_fraction": self.target_fraction,
            "adjusted_fraction": self.adjusted_fraction,
            "guard_decision": self.guard_decision,
            "anomaly_score": self.anomaly_score,
            "sentiment_score": self.sentiment_score,
            "price": self.price,
            "features_shape": list(self.features_shape),
            "error": self.error,
        }


@dataclass
class GhostMachineConfig:
    """Configuration for the autonomous trading loop."""
    # Symbols to trade
    symbols: List[str] = field(default_factory=lambda: ["BTC/USDT"])
    # Loop interval in seconds (how often to check market)
    cycle_interval: float = 60.0
    # Timeframe for candles
    timeframe: str = "5m"
    # Number of historical candles to fetch each cycle
    candle_lookback: int = 200
    # Starting cash for paper trading
    starting_cash: float = 100.0
    # Max leverage
    max_leverage: float = 20.0
    # Enable live execution (False = paper trading only)
    live_mode: bool = False
    # AutoML interval in seconds (default 7 days)
    automl_interval: float = 7 * 24 * 3600.0
    # Enable anomaly guard
    anomaly_guard_enabled: bool = True
    # Enable MiMo supervisor
    mimo_supervisor_enabled: bool = True
    # Max consecutive errors before pause
    max_consecutive_errors: int = 10
    # Pause duration after max errors (seconds)
    error_pause_duration: float = 300.0


class GhostMachine:
    """
    Autonomous 24/7 trading loop.
    
    Orchestrates:
    - Live data fetching (CCXT)
    - Feature computation (FeatureStore)
    - RL prediction (SB3 PPO/SAC)
    - Anomaly guarding (IsolationForest + MiMo)
    - Order execution (CCXT / PaperBroker)
    
    Usage:
        machine = GhostMachine(config)
        machine.start()  # Runs in background thread
        
        # Or for manual control:
        result = machine.run_single_cycle()
        
        machine.stop()
    """

    def __init__(
        self,
        config: Optional[GhostMachineConfig] = None,
        rl_agent=None,
        feature_store=None,
        executor=None,
        anomaly_guard=None,
        sentiment_scheduler=None,
    ):
        """
        Initialize Ghost Machine.
        
        Args:
            config: Trading loop configuration
            rl_agent: RLTradingAgent instance (from src/rl/agent_integration.py)
            feature_store: FeatureStore instance (from src/ml/feature_store.py)
            executor: ExecutionManager or PaperBroker
            anomaly_guard: AnomalyExecutionGuard (from src/execution/anomaly_guard.py)
            sentiment_scheduler: SentimentScheduler (from src/pipeline/scheduler.py)
        """
        self.config = config or GhostMachineConfig()
        self._rl_agent = rl_agent
        self._feature_store = feature_store
        self._executor = executor
        self._anomaly_guard = anomaly_guard
        self._sentiment_scheduler = sentiment_scheduler

        # State
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._consecutive_errors = 0
        self._paused = False

        # History
        self.cycle_history: List[TradingCycleResult] = []
        self._max_history = 2000

        # Stats
        self.stats = {
            "total_cycles": 0,
            "successful_cycles": 0,
            "failed_cycles": 0,
            "trades_executed": 0,
            "trades_blocked": 0,
            "trades_reduced": 0,
            "start_time": None,
            "last_cycle_time": None,
            "uptime_seconds": 0.0,
        }

    def _lazy_import(self):
        """Lazy import dependencies."""
        modules = {}
        try:
            from src.pipeline.data_connectors.hf_connector import HfConnector
            modules["hf_connector"] = HfConnector
        except ImportError:
            logger.warning("HfConnector not available")

        try:
            from src.ml.feature_store import FeatureStore
            modules["feature_store"] = FeatureStore
        except ImportError:
            logger.warning("FeatureStore not available")

        return modules

    def start(self) -> None:
        """Start the autonomous trading loop in a background thread."""
        if self._running:
            logger.warning("Ghost Machine already running")
            return

        self._stop_event.clear()
        self._running = True
        self._paused = False
        self._consecutive_errors = 0
        self.stats["start_time"] = datetime.now(timezone.utc).isoformat()

        self._thread = threading.Thread(
            target=self._run_loop,
            name="GhostMachine",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            f"Ghost Machine started | symbols={self.config.symbols} | "
            f"interval={self.config.cycle_interval}s | "
            f"live={'ON' if self.config.live_mode else 'PAPER'}"
        )

    def stop(self, timeout: float = 30.0) -> None:
        """Stop the trading loop gracefully."""
        if not self._running:
            return

        self._stop_event.set()
        self._running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        uptime = 0.0
        if self.stats["start_time"]:
            try:
                start = datetime.fromisoformat(self.stats["start_time"])
                uptime = (datetime.now(timezone.utc) - start).total_seconds()
            except Exception:
                pass
        self.stats["uptime_seconds"] = uptime

        logger.info(
            f"Ghost Machine stopped | cycles={self.stats['total_cycles']} | "
            f"trades={self.stats['trades_executed']} | "
            f"blocked={self.stats['trades_blocked']} | "
            f"uptime={uptime:.0f}s"
        )

    @property
    def is_running(self) -> bool:
        return self._running

    def _run_loop(self) -> None:
        """Main trading loop."""
        logger.info("Ghost Machine loop started")

        while not self._stop_event.is_set():
            try:
                # Handle pause (error recovery)
                if self._paused:
                    logger.info(
                        f"Ghost Machine paused due to errors. "
                        f"Resuming in {self.config.error_pause_duration}s..."
                    )
                    if self._stop_event.wait(self.config.error_pause_duration):
                        break
                    self._paused = False
                    self._consecutive_errors = 0
                    logger.info("Ghost Machine resumed after error pause")

                # Run a single trading cycle for each symbol
                for symbol in self.config.symbols:
                    if self._stop_event.is_set():
                        break
                    result = self._process_symbol(symbol)
                    self._record_cycle(result)

                self._consecutive_errors = 0

            except Exception as e:
                self._consecutive_errors += 1
                self.stats["failed_cycles"] += 1
                logger.error(
                    f"Ghost Machine cycle error ({self._consecutive_errors}/"
                    f"{self.config.max_consecutive_errors}): {e}",
                    exc_info=True,
                )

                if self._consecutive_errors >= self.config.max_consecutive_errors:
                    self._paused = True
                    logger.critical(
                        f"Ghost Machine entering error pause after "
                        f"{self._consecutive_errors} consecutive errors"
                    )

            # Wait for next cycle
            if self._stop_event.is_set():
                break
            self._stop_event.wait(self.config.cycle_interval)

        logger.info("Ghost Machine loop exited")

    def _process_symbol(self, symbol: str) -> TradingCycleResult:
        """
        Process a single trading cycle for one symbol.
        
        Steps:
        1. Fetch latest candles
        2. Compute features
        3. Get sentiment vector (if available)
        4. RL agent predicts action
        5. Anomaly guard evaluates
        6. Execute or block order
        """
        ts = datetime.now(timezone.utc).isoformat()

        try:
            # 1. Fetch live candles
            modules = self._lazy_import()
            HfConnector = modules.get("hf_connector")
            if HfConnector is None:
                return TradingCycleResult(
                    symbol=symbol, timestamp=ts, action_taken="ERROR",
                    target_fraction=0.0, adjusted_fraction=0.0,
                    guard_decision="error", anomaly_score=0.0,
                    sentiment_score=0.0, price=0.0, features_shape=(0,),
                    error="HfConnector not available",
                )

            connector = HfConnector()
            candles = connector.fetch_ohlcv(
                symbol=symbol,
                timeframe=self.config.timeframe,
                limit=self.config.candle_lookback,
            )

            if candles is None or len(candles) == 0:
                return TradingCycleResult(
                    symbol=symbol, timestamp=ts, action_taken="ERROR",
                    target_fraction=0.0, adjusted_fraction=0.0,
                    guard_decision="error", anomaly_score=0.0,
                    sentiment_score=0.0, price=0.0, features_shape=(0,),
                    error="No candle data received",
                )

            current_price = float(candles["close"].iloc[-1])
            prices = candles["close"].values
            volumes = candles["volume"].values

            # 2. Compute features
            if self._feature_store is not None:
                features = self._feature_store.compute_features(
                    candles, symbol=symbol
                )
            else:
                # Basic features from candles
                import pandas as pd
                returns = pd.Series(prices).pct_change().fillna(0).values
                features = pd.DataFrame({
                    "returns": returns,
                    "volume": volumes,
                    "volatility": pd.Series(returns).rolling(20).std().fillna(0),
                })

            # 3. Get sentiment vector
            sentiment_vector = None
            sentiment_score = 0.0
            if self._sentiment_scheduler is not None:
                try:
                    sentiment_vector = self._sentiment_scheduler.get_latest_vector(symbol)
                    if sentiment_vector is not None and len(sentiment_vector) > 0:
                        sentiment_score = float(sentiment_vector[0])
                except Exception as e:
                    logger.debug(f"Sentiment fetch failed: {e}")

            # 4. RL agent prediction
            if self._rl_agent is None:
                return TradingCycleResult(
                    symbol=symbol, timestamp=ts, action_taken="HOLD",
                    target_fraction=0.0, adjusted_fraction=0.0,
                    guard_decision="no_agent", anomaly_score=0.0,
                    sentiment_score=sentiment_score,
                    price=current_price, features_shape=tuple(features.shape),
                    error="No RL agent configured",
                )

            # Prepare observation for RL agent
            if isinstance(features, np.ndarray):
                obs = features
            else:
                obs = features.values

            # Use last row as observation (flatten if needed)
            if obs.ndim > 1:
                obs_flat = obs[-1].flatten().astype(np.float32)
            else:
                obs_flat = obs.flatten().astype(np.float32)

            # RL prediction
            target_fraction = self._rl_agent.predict(
                obs_flat,
                sentiment_vector=sentiment_vector,
            )

            # If predict returns array, take first element
            if hasattr(target_fraction, '__len__') and not isinstance(target_fraction, str):
                target_fraction = float(target_fraction[0]) if len(target_fraction) > 0 else 0.0
            else:
                target_fraction = float(target_fraction)

            # 5. Anomaly guard evaluation
            guard_decision = "pass"
            adjusted_fraction = target_fraction
            anomaly_score = 0.0

            if self._anomaly_guard is not None and self.config.anomaly_guard_enabled:
                guard_result = self._anomaly_guard.evaluate(
                    target_fraction=target_fraction,
                    features=obs_flat.reshape(1, -1),
                    prices=prices,
                    volumes=volumes,
                )
                guard_decision = guard_result.decision.value
                adjusted_fraction = guard_result.adjusted_fraction
                anomaly_score = guard_result.anomaly_score

                if guard_result.is_blocked:
                    self.stats["trades_blocked"] += 1
                    return TradingCycleResult(
                        symbol=symbol, timestamp=ts, action_taken="BLOCKED",
                        target_fraction=target_fraction,
                        adjusted_fraction=0.0,
                        guard_decision=guard_decision,
                        anomaly_score=anomaly_score,
                        sentiment_score=sentiment_score,
                        price=current_price,
                        features_shape=tuple(features.shape),
                    )
                elif guard_result.is_reduced:
                    self.stats["trades_reduced"] += 1

            # 6. Determine action and execute
            action_taken = "HOLD"
            if abs(adjusted_fraction) > 0.01:
                action_taken = "BUY" if adjusted_fraction > 0 else "SELL"

                if self._executor is not None:
                    try:
                        self._execute_order(
                            symbol=symbol,
                            fraction=adjusted_fraction,
                            price=current_price,
                        )
                        self.stats["trades_executed"] += 1
                    except Exception as e:
                        logger.error(f"Execution failed for {symbol}: {e}")
                        action_taken = "EXEC_ERROR"

            self.stats["successful_cycles"] += 1

            return TradingCycleResult(
                symbol=symbol, timestamp=ts, action_taken=action_taken,
                target_fraction=target_fraction,
                adjusted_fraction=adjusted_fraction,
                guard_decision=guard_decision,
                anomaly_score=anomaly_score,
                sentiment_score=sentiment_score,
                price=current_price,
                features_shape=tuple(features.shape),
            )

        except Exception as e:
            logger.error(f"Cycle processing error for {symbol}: {e}", exc_info=True)
            return TradingCycleResult(
                symbol=symbol, timestamp=ts, action_taken="ERROR",
                target_fraction=0.0, adjusted_fraction=0.0,
                guard_decision="error", anomaly_score=0.0,
                sentiment_score=0.0, price=0.0, features_shape=(0,),
                error=str(e),
            )

    def _execute_order(self, symbol: str, fraction: float, price: float) -> None:
        """Execute an order through the execution manager."""
        if self._executor is None:
            return

        try:
            # Calculate notional value
            notional = abs(fraction) * self.config.starting_cash * self.config.max_leverage
            side = "buy" if fraction > 0 else "sell"

            if self.config.live_mode:
                logger.info(
                    f"LIVE ORDER: {side.upper()} {symbol} "
                    f"notional=${notional:.2f} fraction={fraction:.4f}"
                )
            else:
                logger.info(
                    f"PAPER ORDER: {side.upper()} {symbol} "
                    f"notional=${notional:.2f} fraction={fraction:.4f}"
                )

            # Delegate to executor (abstract interface)
            if hasattr(self._executor, 'submit_order'):
                self._executor.submit_order(
                    symbol=symbol,
                    side=side,
                    notional=notional,
                    price=price,
                )
            elif hasattr(self._executor, 'execute'):
                self._executor.execute(
                    symbol=symbol,
                    side=side,
                    notional=notional,
                    price=price,
                )

        except Exception as e:
            logger.error(f"Order execution error: {e}")
            raise

    def _record_cycle(self, result: TradingCycleResult) -> None:
        """Record a cycle result."""
        self.stats["total_cycles"] += 1
        self.stats["last_cycle_time"] = result.timestamp

        self.cycle_history.append(result)
        if len(self.cycle_history) > self._max_history:
            self.cycle_history = self.cycle_history[-self._max_history:]

    def run_single_cycle(self, symbol: Optional[str] = None) -> List[TradingCycleResult]:
        """
        Run a single trading cycle (for testing/manual trigger).
        
        Args:
            symbol: Symbol to trade (defaults to all config symbols)
            
        Returns:
            List of cycle results
        """
        symbols = [symbol] if symbol else self.config.symbols
        results = []

        for sym in symbols:
            result = self._process_symbol(sym)
            self._record_cycle(result)
            results.append(result)

        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics."""
        uptime = self.stats.get("uptime_seconds", 0.0)
        if self._running and self.stats["start_time"]:
            try:
                start = datetime.fromisoformat(self.stats["start_time"])
                uptime = (datetime.now(timezone.utc) - start).total_seconds()
            except Exception:
                pass

        return {
            **self.stats,
            "is_running": self._running,
            "is_paused": self._paused,
            "consecutive_errors": self._consecutive_errors,
            "uptime_seconds": uptime,
            "cycle_history_size": len(self.cycle_history),
            "recent_cycles": [c.to_dict() for c in self.cycle_history[-5:]],
        }

    def get_recent_trades(self, n: int = 20) -> List[Dict[str, Any]]:
        """Get recent trade actions."""
        trades = [
            c for c in self.cycle_history
            if c.action_taken in ("BUY", "SELL")
        ]
        return [c.to_dict() for c in trades[-n:]]