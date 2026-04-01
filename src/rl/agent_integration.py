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
Indonesia compliance: IDX, OJK, BEI rules
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
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
    holdings: Dict[str, int] = field(default_factory=dict)  # symbol -> qty
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
    Manages positions with IDX compliance:
    - Minimum lot size: 100 shares
    - Maximum leverage: Conservative limits
    - Trade tracking and P&L
    """
    
    def __init__(
        self,
        starting_capital: float = 1_000_000.0,
        min_lot_size: int = 100,
        max_leverage: float = 0.8,
        commission_pct: float = 0.0008,
    ):
        """
        Initialize position manager.
        
        Args:
            starting_capital: Initial cash in IDR
            min_lot_size: Minimum shares per lot (IDX: 100)
            max_leverage: Max fraction of capital to leverage
            commission_pct: Transaction cost percentage
        """
        self.starting_capital = float(starting_capital)
        self.cash = float(starting_capital)
        self.min_lot_size = int(min_lot_size)
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
                unrealized_pnl[symbol] = (current_price - self.entry_prices.get(symbol, 0)) * qty
                total_value += qty * current_price
        
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
    
    def should_trade(self, symbol: str, target_qty: int, price: float) -> Tuple[bool, str]:
        """
        Check if trade is allowed (IDX compliance).
        
        Returns:
            (allowed, reason)
        """
        # Check minimum lot size
        if target_qty > 0 and target_qty % self.min_lot_size != 0:
            return False, f"Qty {target_qty} not multiple of {self.min_lot_size}"
        
        # Check available cash for buy
        current_qty = self.holdings.get(symbol, 0)
        if target_qty > current_qty:
            qty_to_buy = target_qty - current_qty
            cost = qty_to_buy * price * (1.0 + self.commission_pct)
            if cost > self.cash:
                return False, f"Insufficient cash: need {cost:.2f}, have {self.cash:.2f}"
        
        # Check max leverage
        current_notional = current_qty * price
        new_notional = target_qty * price
        max_notional = self.max_leverage * (self.cash + current_notional)
        if new_notional > max_notional:
            return False, f"Would exceed max leverage ({max_notional:.2f})"
        
        return True, "OK"
    
    def execute_trade(
        self,
        symbol: str,
        action: str,  # "buy" or "sell"
        qty: int,
        price: float,
        reason: str = "RL action",
    ) -> Dict[str, Any]:
        """
        Execute a trade.
        
        Returns:
            Trade result dict
        """
        allowed, msg = self.should_trade(symbol, qty if action == "buy" else self.holdings.get(symbol, 0) - qty, price)
        if not allowed:
            return {"status": "rejected", "reason": msg}
        
        current_qty = self.holdings.get(symbol, 0)
        commission = 0.0
        
        if action == "buy":
            qty_to_buy = qty - current_qty
            if qty_to_buy > 0:
                cost = qty_to_buy * price * (1.0 + self.commission_pct)
                if cost <= self.cash:
                    self.cash -= cost
                    self.holdings[symbol] = qty
                    self.entry_prices[symbol] = price
                    commission = qty_to_buy * price * self.commission_pct
        
        elif action == "sell":
            qty_to_sell = current_qty - qty
            if qty_to_sell > 0:
                proceeds = qty_to_sell * price * (1.0 - self.commission_pct)
                self.cash += proceeds
                self.holdings[symbol] = qty
                commission = qty_to_sell * price * self.commission_pct
                
                # Track P&L
                pnl = (price - self.entry_prices.get(symbol, 0)) * qty_to_sell
                if pnl > 0:
                    self.win_count += 1
                else:
                    self.loss_count += 1
                self.pnl_history.append(pnl)
        
        self.trade_history.append({
            "symbol": symbol,
            "action": action,
            "qty": qty,
            "price": price,
            "commission": commission,
            "timestamp": get_jakarta_now(),
            "reason": reason,
        })
        
        return {"status": "executed", "commission": commission}


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
    - Position management (IDX compliance)
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
            min_lot_size=100,
            max_leverage=0.8,
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
    ) -> Dict[str, int]:
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
            
            # Calculate target quantity
            target_qty = int((target_fraction * self.position_manager.cash) / price)
            target_qty = (target_qty // 100) * 100  # Round to nearest lot
            
            current_qty = self.position_manager.holdings.get(symbol, 0)
            
            if target_qty > current_qty:
                action_type = "buy"
                qty = target_qty
            elif target_qty < current_qty:
                action_type = "sell"
                qty = target_qty
            else:
                continue
            
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
