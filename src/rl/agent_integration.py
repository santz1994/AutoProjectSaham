"""
Agent Integration Module (Task 11)
==================================

Real-time RL agent inference and trading system integration.

Integrates:
- Trained PPO/SAC policies
- Anomaly detection (Task 9)
- Regime detection (Task 10)
- Online learning (Task 7)
- Meta-learning (Task 8)
- ExecutionManager for order placement
- Portfolio risk monitoring

Jakarta timezone: WIB (UTC+7)
Forex/Crypto scope for 24x5/24x7 execution paths
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import logging

try:
    from stable_baselines3 import PPO, SAC
    STABLE_BASELINES3_AVAILABLE = True
except ImportError:
    STABLE_BASELINES3_AVAILABLE = False

logger = logging.getLogger(__name__)

# Jakarta timezone
JAKARTA_TZ = timezone(timedelta(hours=7))


def get_jakarta_now() -> datetime:
    """Get current time in Jakarta (WIB)."""
    return datetime.now(JAKARTA_TZ)


# ============================================================================
# Portfolio State Manager
# ============================================================================

@dataclass
class PortfolioState:
    """Current portfolio state."""
    total_value: float = 0.0
    cash: float = 0.0
    holdings: Dict[str, float] = field(default_factory=dict)  # symbol -> qty
    entry_prices: Dict[str, float] = field(default_factory=dict)
    unrealized_pnl: Dict[str, float] = field(default_factory=dict)
    max_drawdown: float = 0.0
    daily_return: float = 0.0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    timestamp: Optional[datetime] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "total_value": self.total_value,
            "cash": self.cash,
            "holdings": self.holdings,
            "entry_prices": self.entry_prices,
            "unrealized_pnl": self.unrealized_pnl,
            "max_drawdown": self.max_drawdown,
            "daily_return": self.daily_return,
            "win_rate": self.win_rate,
            "sharpe_ratio": self.sharpe_ratio,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


# ============================================================================
# Position Manager
# ============================================================================

class PositionManager:
    """
    Manages positions for leveraged forex/crypto style execution:
    - Optional lot-size guard (disabled by default)
    - Fractional quantity support
    - Trade tracking and P&L
    """
    
    def __init__(
        self,
        starting_capital: float = 1_000_000.0,
        min_lot_size: float = 0.0,
        max_leverage: float = 20.0,
        commission_pct: float = 0.0008,
    ):
        """
        Initialize position manager.
        
        Args:
            starting_capital: Initial cash in IDR
            min_lot_size: Optional discrete lot size (0 disables lot checks)
            max_leverage: Max fraction of capital to leverage
            commission_pct: Transaction cost percentage
        """
        self.starting_capital = float(starting_capital)
        self.cash = float(starting_capital)
        self.min_lot_size = float(max(0.0, min_lot_size))
        self.max_leverage = float(max_leverage)
        self.commission_pct = float(commission_pct)
        
        self.holdings = {}  # {symbol: qty}
        self.entry_prices = {}  # {symbol: entry_price}
        self.trade_history = []
        self.portfolio_values = [starting_capital]
        self.pnl_history = []
        self.win_count = 0
        self.loss_count = 0
    
    def get_state(self, current_prices: Dict[str, float]) -> PortfolioState:
        """Get current portfolio state."""
        total_value = self.cash
        unrealized_pnl = {}
        
        for symbol, qty in self.holdings.items():
            if qty > 0 and symbol in current_prices:
                current_price = current_prices[symbol]
                unrealized = (
                    current_price - self.entry_prices.get(symbol, current_price)
                ) * qty
                unrealized_pnl[symbol] = unrealized
                total_value += unrealized
        
        daily_return = 0.0
        if len(self.portfolio_values) > 1:
            daily_return = (total_value - self.portfolio_values[-1]) / self.portfolio_values[-1]
        
        max_drawdown = (min(self.portfolio_values) - self.starting_capital) / self.starting_capital if self.portfolio_values else 0.0
        
        win_rate = self.win_count / (self.win_count + self.loss_count) if (self.win_count + self.loss_count) > 0 else 0.0
        
        # Simple Sharpe computation
        if len(self.pnl_history) > 1:
            mean_pnl = np.mean(self.pnl_history)
            std_pnl = np.std(self.pnl_history)
            sharpe = (mean_pnl / std_pnl * np.sqrt(252)) if std_pnl > 0 else 0.0
        else:
            sharpe = 0.0
        
        state = PortfolioState(
            total_value=total_value,
            cash=self.cash,
            holdings=dict(self.holdings),
            entry_prices=dict(self.entry_prices),
            unrealized_pnl=unrealized_pnl,
            max_drawdown=max_drawdown,
            daily_return=daily_return,
            win_rate=win_rate,
            sharpe_ratio=sharpe,
            timestamp=get_jakarta_now(),
        )
        
        return state
    
    def should_trade(
        self,
        symbol: str,
        target_qty: float,
        price: float,
    ) -> Tuple[bool, str]:
        """
        Check if target position is allowed.
        
        Returns:
            (allowed, reason)
        """
        safe_target_qty = float(target_qty)
        safe_price = float(price)

        if not math.isfinite(safe_target_qty) or safe_target_qty < 0:
            return False, "target_qty must be >= 0"
        if not math.isfinite(safe_price) or safe_price <= 0:
            return False, "price must be > 0"

        # Optional lot-size compatibility guard.
        if self.min_lot_size > 0 and safe_target_qty > 0:
            lot_units = safe_target_qty / self.min_lot_size
            if not np.isclose(lot_units, round(lot_units), atol=1e-9):
                return False, (
                    f"Qty {safe_target_qty} not multiple of {self.min_lot_size}"
                )
        
        current_qty = float(self.holdings.get(symbol, 0.0))

        # Margin-style affordability check for incremental buy.
        if safe_target_qty > current_qty:
            qty_to_buy = safe_target_qty - current_qty
            buy_notional = qty_to_buy * safe_price
            effective_lev = max(self.max_leverage, 1e-6)
            required_margin = buy_notional / effective_lev
            estimated_fee = buy_notional * self.commission_pct
            required_cash = required_margin + estimated_fee
            if required_cash > self.cash:
                return False, (
                    f"Insufficient cash: need {required_cash:.2f}, have {self.cash:.2f}"
                )
        
        # Cap absolute position notional by current equity.
        equity = max(self.cash, 1e-6)
        new_notional = safe_target_qty * safe_price
        max_notional = max(0.0, self.max_leverage) * equity
        if new_notional > max_notional:
            return False, f"Would exceed max leverage ({max_notional:.2f})"
        
        return True, "OK"
    
    def execute_trade(
        self,
        symbol: str,
        action: str,  # "buy" or "sell"
        qty: float,
        price: float,
        reason: str = "RL action",
    ) -> Dict[str, Any]:
        """
        Execute a trade.
        
        Returns:
            Trade result dict
        """
        action_l = str(action or "").strip().lower()
        if action_l not in {"buy", "sell"}:
            return {"status": "rejected", "reason": "unknown_action"}

        requested_qty = float(qty)
        if not math.isfinite(requested_qty) or requested_qty <= 0:
            return {"status": "rejected", "reason": "qty must be > 0"}

        current_qty = float(self.holdings.get(symbol, 0.0))
        if action_l == "buy":
            target_qty = current_qty + requested_qty
        else:
            if requested_qty > current_qty + 1e-12:
                return {
                    "status": "rejected",
                    "reason": "insufficient_position",
                }
            target_qty = max(0.0, current_qty - requested_qty)

        allowed, msg = self.should_trade(symbol, target_qty, price)
        if not allowed:
            return {"status": "rejected", "reason": msg}
        
        commission = 0.0
        realized_pnl = 0.0
        
        if action_l == "buy":
            qty_to_buy = requested_qty
            if qty_to_buy > 0:
                notional = qty_to_buy * float(price)
                commission = notional * self.commission_pct
                self.cash -= commission

                prev_entry = float(self.entry_prices.get(symbol, float(price)))
                next_qty = current_qty + qty_to_buy
                weighted_entry = (
                    ((prev_entry * current_qty) + (float(price) * qty_to_buy))
                    / max(next_qty, 1e-12)
                )

                self.holdings[symbol] = next_qty
                self.entry_prices[symbol] = weighted_entry

        elif action_l == "sell":
            qty_to_sell = requested_qty
            if qty_to_sell > 0:
                entry_price = float(self.entry_prices.get(symbol, float(price)))
                realized_pnl = (float(price) - entry_price) * qty_to_sell
                commission = qty_to_sell * float(price) * self.commission_pct
                self.cash += realized_pnl - commission

                if target_qty <= 1e-12:
                    self.holdings.pop(symbol, None)
                    self.entry_prices.pop(symbol, None)
                else:
                    self.holdings[symbol] = target_qty

                # Track realized P&L
                if realized_pnl > 0:
                    self.win_count += 1
                else:
                    self.loss_count += 1
                self.pnl_history.append(realized_pnl)
        
        self.trade_history.append({
            "symbol": symbol,
            "action": action_l,
            "qty": requested_qty,
            "target_qty": target_qty,
            "price": price,
            "commission": commission,
            "realized_pnl": realized_pnl,
            "timestamp": get_jakarta_now(),
            "reason": reason,
        })
        
        return {
            "status": "executed",
            "commission": commission,
            "realized_pnl": realized_pnl,
        }


# ============================================================================
# RL Agent for Trading
# ============================================================================

class RLTradingAgent:
    """
    RL agent for live trading with full integration.
    
    Features:
    - PPO or SAC policy
    - Anomaly detection integration (Task 9)
    - Regime detection integration (Task 10)
    - Fractional position management for forex/crypto
    - Risk monitoring
    - Performance tracking
    """
    
    def __init__(
        self,
        model_path: str,
        symbols: List[str],
        anomaly_detector: Optional[Any] = None,
        regime_detector: Optional[Any] = None,
        online_learner: Optional[Any] = None,
        meta_learner: Optional[Any] = None,
        starting_capital: float = 1_000_000.0,
        model_type: str = "auto",  # or "ppo", "sac"
    ):
        """
        Initialize RL trading agent.
        
        Args:
            model_path: Path to trained model
            symbols: List of trading symbols
            anomaly_detector: Task 9 anomaly detector
            regime_detector: Task 10 regime detector
            online_learner: Task 7 online learner
            meta_learner: Task 8 meta learner
            starting_capital: Initial capital in IDR
            model_type: "auto", "ppo", or "sac"
        """
        if not STABLE_BASELINES3_AVAILABLE:
            raise RuntimeError("stable-baselines3 required")
        
        self.model_path = model_path
        self.symbols = sorted(symbols)
        self.anomaly_detector = anomaly_detector
        self.regime_detector = regime_detector
        self.online_learner = online_learner
        self.meta_learner = meta_learner
        
        # Load model
        self.model = self._load_model(model_path, model_type)
        
        # Position management
        self.position_manager = PositionManager(
            starting_capital=starting_capital,
            min_lot_size=0.0,
            max_leverage=20.0,
            commission_pct=0.0008,
        )
        
        # Inference tracking
        self.inference_count = 0
        self.last_inference_time = None
        self.last_observation = None
        self.last_action = None
        
        logger.info(f"Initialized RLTradingAgent with model from {model_path}")
    
    def _load_model(self, path: str, model_type: str):
        """Load trained model."""
        try:
            if model_type == "auto":
                # Try to infer from path or try both
                try:
                    return PPO.load(path)
                except:
                    return SAC.load(path)
            elif model_type == "ppo":
                return PPO.load(path)
            elif model_type == "sac":
                return SAC.load(path)
            else:
                raise ValueError(f"Unknown model_type: {model_type}")
        except Exception as e:
            logger.error(f"Failed to load model from {path}: {e}")
            raise
    
    def predict(
        self,
        features: np.ndarray,
        deterministic: bool = False,
    ) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        """
        Get action from trained policy.
        
        Args:
            features: Observation vector from environment
            deterministic: Use mean action (no exploration)
        
        Returns:
            (action, state) for the policy
        """
        self.last_observation = features.copy()
        action, state = self.model.predict(
            features,
            deterministic=deterministic,
        )
        self.last_action = action.copy() if isinstance(action, np.ndarray) else action
        self.inference_count += 1
        self.last_inference_time = get_jakarta_now()
        
        return action, state
    
    def get_positions(
        self,
        current_prices: Dict[str, float],
    ) -> Dict[str, float]:
        """Get current positions."""
        return dict(self.position_manager.holdings)
    
    def get_portfolio_state(
        self,
        current_prices: Dict[str, float],
    ) -> PortfolioState:
        """Get current portfolio state."""
        return self.position_manager.get_state(current_prices)
    
    def process_action(
        self,
        action: np.ndarray,
        current_prices: Dict[str, float],
        anomaly_flags: Optional[Dict[str, bool]] = None,
        regime_state: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Process RL action into trades.
        
        Args:
            action: Action from policy [0, 1] for each symbol
            current_prices: Current prices for all symbols
            anomaly_flags: Anomaly detection flags
            regime_state: Current regime states
        
        Returns:
            Execution results
        """
        action = np.clip(action, 0.0, 1.0)
        
        trades = []
        
        for i, symbol in enumerate(self.symbols):
            if i >= len(action):
                break
            
            target_fraction = float(action[i])
            price = current_prices.get(symbol, 0.0)
            
            if price <= 0:
                logger.warning(f"Invalid price for {symbol}: {price}")
                continue
            
            # Apply anomaly detection (Task 9)
            if anomaly_flags and anomaly_flags.get(symbol, False):
                target_fraction *= 0.5  # Reduce position
                logger.info(f"Anomaly detected in {symbol}, reducing position to {target_fraction:.2%}")
            
            # Apply regime detection (Task 10)
            if regime_state and symbol in regime_state and self.regime_detector:
                try:
                    regime = regime_state[symbol]
                    params = self.regime_detector.get_strategy_params(regime)
                    risk_mult = params.get("risk_multiplier", 1.0)
                    target_fraction *= risk_mult
                except Exception as e:
                    logger.warning(f"Regime adjustment failed for {symbol}: {e}")
            
            target_fraction = float(np.clip(target_fraction, 0.0, 1.0))

            # Fractional quantity sizing: target notional = fraction of
            # leverage-adjusted buying capacity.
            buying_capacity = (
                self.position_manager.cash * max(self.position_manager.max_leverage, 0.0)
            )
            target_notional = target_fraction * buying_capacity
            target_qty = target_notional / float(price)

            if self.position_manager.min_lot_size > 0:
                lot = self.position_manager.min_lot_size
                target_qty = math.floor(target_qty / lot) * lot

            target_qty = round(max(0.0, target_qty), 8)
            
            current_qty = float(self.position_manager.holdings.get(symbol, 0.0))
            
            if abs(target_qty - current_qty) <= 1e-8:
                continue

            if target_qty > current_qty:
                action_type = "buy"
                qty = target_qty - current_qty
            else:
                action_type = "sell"
                qty = current_qty - target_qty
            
            result = self.position_manager.execute_trade(
                symbol=symbol,
                action=action_type,
                qty=qty,
                price=price,
                reason="RL policy inference",
            )
            
            trades.append({
                "symbol": symbol,
                "action": action_type,
                "qty": qty,
                "price": price,
                "result": result,
            })
        
        return {
            "trades": trades,
            "portfolio_state": self.position_manager.get_state(current_prices),
            "timestamp": get_jakarta_now(),
        }
    
    def save_checkpoint(self, path: str) -> bool:
        """Save agent checkpoint."""
        try:
            checkpoint_data = {
                "model_path": self.model_path,
                "symbols": self.symbols,
                "position_manager": {
                    "cash": self.position_manager.cash,
                    "holdings": self.position_manager.holdings,
                    "entry_prices": self.position_manager.entry_prices,
                    "trade_history": self.position_manager.trade_history,
                    "portfolio_values": self.position_manager.portfolio_values,
                    "pnl_history": self.position_manager.pnl_history,
                },
                "inference_count": self.inference_count,
                "timestamp": get_jakarta_now().isoformat(),
            }
            
            import json
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                json.dump(checkpoint_data, f, indent=2, default=str)
            
            logger.info(f"Saved agent checkpoint to {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get agent statistics."""
        return {
            "model_path": self.model_path,
            "symbols": self.symbols,
            "inference_count": self.inference_count,
            "last_inference_time": self.last_inference_time.isoformat() if self.last_inference_time else None,
            "last_action": self.last_action.tolist() if isinstance(self.last_action, np.ndarray) else None,
            "position_manager": {
                "cash": self.position_manager.cash,
                "holdings": self.position_manager.holdings,
                "trade_count": len(self.position_manager.trade_history),
                "win_count": self.position_manager.win_count,
                "loss_count": self.position_manager.loss_count,
                "total_trades": self.position_manager.win_count + self.position_manager.loss_count,
            },
        }


# ============================================================================
# Batch Inference Engine
# ============================================================================

class BatchInferenceEngine:
    """Process batches of observations for efficient multi-symbol inference."""
    
    def __init__(self, agent: RLTradingAgent, batch_size: int = 32):
        """
        Initialize batch inference.
        
        Args:
            agent: RLTradingAgent instance
            batch_size: Batch size for vectorized inference
        """
        self.agent = agent
        self.batch_size = batch_size
        self.pending_observations = []
        self.pending_symbols = []
    
    def add_observation(self, symbol: str, observation: np.ndarray) -> None:
        """Queue observation for batch processing."""
        self.pending_observations.append(observation)
        self.pending_symbols.append(symbol)
    
    def process_batch(self, deterministic: bool = False) -> Dict[str, np.ndarray]:
        """
        Process pending observations.
        
        Returns:
            {symbol: action} mapping
        """
        if not self.pending_observations:
            return {}
        
        results = {}
        
        # Process in batches
        for i in range(0, len(self.pending_observations), self.batch_size):
            batch_obs = np.array(self.pending_observations[i:i+self.batch_size])
            batch_symbols = self.pending_symbols[i:i+self.batch_size]
            
            # Vectorized prediction if model supports it
            try:
                actions, _ = self.agent.model.predict(batch_obs, deterministic=deterministic)
                for symbol, action in zip(batch_symbols, actions):
                    results[symbol] = action
            except Exception as e:
                logger.warning(f"Batch prediction failed: {e}, falling back to sequential")
                for obs, symbol in zip(batch_obs, batch_symbols):
                    action, _ = self.agent.predict(obs, deterministic=deterministic)
                    results[symbol] = action
        
        # Clear pending
        self.pending_observations = []
        self.pending_symbols = []
        
        return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Agent Integration Module (Task 11) - Ready for import")
