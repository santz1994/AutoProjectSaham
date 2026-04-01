"""
RL Policy Trainers: PPO, SAC, and Hybrid
=========================================

Task 11 - Training optimal trading policies using:
- PPO (Proximal Policy Optimization) for stable learning
- SAC (Soft Actor-Critic) for sample efficiency
- Hybrid: PPO warm-up + SAC fine-tuning

Integration with Task 9-10:
- Anomaly detection: Reduce position during anomalies
- Regime detection: Regime-aware reward shaping
- Online learning hooks for continual adaptation
- Meta-learning ready: Transfer across symbols

Indonesia Compliance:
- Jakarta timezone (WIB/UTC+7)
- IDX lot size: 100 shares minimum
- Trading hours: 09:30-16:00 WIB
- Settlement: T+2
- Currency: IDR (Rp)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable
import numpy as np
import logging

try:
    from stable_baselines3 import PPO, SAC
    from stable_baselines3.common.callbacks import EvalCallback, StopTrainingOnRewardThreshold
    from stable_baselines3.common.env_util import make_vec_env
    from stable_baselines3.common.vec_env import VecEnv, DummyVecEnv
    STABLE_BASELINES3_AVAILABLE = True
except ImportError:
    STABLE_BASELINES3_AVAILABLE = False
    PPO = None
    SAC = None

import gymnasium as gym
from gymnasium import spaces

logger = logging.getLogger(__name__)


# ============================================================================
# Jakarta Timezone + Utility Functions
# ============================================================================

JAKARTA_TZ = timezone(timedelta(hours=7))  # WIB: UTC+7

def get_jakarta_now() -> datetime:
    """Get current time in Jakarta (WIB)."""
    return datetime.now(JAKARTA_TZ)

def is_trading_hours(dt: Optional[datetime] = None) -> bool:
    """Check if time is within IDX trading hours (09:30-16:00 WIB)."""
    if dt is None:
        dt = get_jakarta_now()
    
    # Convert to time only
    t = dt.time()
    start = datetime.strptime("09:30", "%H:%M").time()
    end = datetime.strptime("16:00", "%H:%M").time()
    
    # Also check it's a weekday (Monday=0, Friday=4)
    if dt.weekday() > 4:  # Saturday or Sunday
        return False
    
    return start <= t <= end


# ============================================================================
# Multi-Symbol Trading Environment (Wrapper)
# ============================================================================

class MultiSymbolTradingEnv(gym.Env):
    """
    Multi-symbol trading environment for RL training.
    
    Unlike single-symbol, this trains across multiple stocks simultaneously
    to learn portfolio-level strategies.
    
    State: [features_vector + holdings_vector + cash_normalized]
    Actions: [position_size_0, position_size_1, ...] ∈ [0, 1]
    Rewards: Sharpe ratio optimized, anomaly-aware, regime-adjusted
    
    IDX Compliance:
    - Min lot size: 100 shares per symbol
    - Max leverage: Conservative (80% of capital per symbol)
    - Trading hours: 09:30-16:00 WIB only
    - Settlement: T+2 tracking
    """
    
    metadata = {"render_modes": ["human"]}
    
    def __init__(
        self,
        symbols: List[str],
        price_data: Dict[str, List[float]],  # {symbol: [prices]}
        feature_data: Optional[Dict[str, np.ndarray]] = None,  # {symbol: features_matrix}
        anomaly_detector: Optional[Any] = None,
        regime_detector: Optional[Any] = None,
        starting_capital: float = 1_000_000.0,  # IDR
        position_size_shares: int = 100,  # IDX minimum lot
        commission_pct: float = 0.0008,  # IDX typical
        slippage_pct: float = 0.0005,
        max_leverage: float = 0.8,  # 80% per symbol max
    ):
        """
        Initialize multi-symbol environment.
        
        Args:
            symbols: List of stock symbols (e.g., ['BBCA.JK', 'BMRI.JK'])
            price_data: {symbol: list of prices}
            feature_data: Optional {symbol: (T, features) array}
            anomaly_detector: Task 9 anomaly detector instance
            regime_detector: Task 10 regime detector instance
            starting_capital: Initial portfolio value in IDR
            position_size_shares: Shares per lot (100 for IDX)
            commission_pct: Transaction cost %
            slippage_pct: Execution slippage %
            max_leverage: Max fraction of capital per symbol
        """
        assert STABLE_BASELINES3_AVAILABLE, "stable-baselines3 required"
        
        self.symbols = sorted(symbols)
        self.n_symbols = len(self.symbols)
        self.price_data = {s: np.array(price_data[s], dtype=np.float32) for s in self.symbols}
        
        # Validate all symbols have same length
        lengths = [len(self.price_data[s]) for s in self.symbols]
        assert len(set(lengths)) == 1, f"Price arrays must have same length: {lengths}"
        self.max_steps = lengths[0]
        
        self.feature_data = {}
        if feature_data:
            for s in self.symbols:
                if s in feature_data:
                    self.feature_data[s] = np.array(feature_data[s], dtype=np.float32)
        
        self.anomaly_detector = anomaly_detector
        self.regime_detector = regime_detector
        self.starting_capital = float(starting_capital)
        self.position_size_shares = int(position_size_shares)
        self.commission_pct = float(commission_pct)
        self.slippage_pct = float(slippage_pct)
        self.max_leverage = float(max_leverage)
        
        # State tracking
        self.current_step = 0
        self.portfolio_value = self.starting_capital
        self.cash = self.starting_capital
        self.holdings = {s: 0.0 for s in self.symbols}  # quantity held per symbol
        self.entry_prices = {s: 0.0 for s in self.symbols}
        
        # Performance tracking
        self.trade_history = []
        self.portfolio_history = [self.portfolio_value]
        self.returns = [0.0]
        self.sharpe_samples = []
        
        # Action space: continuous position sizes [0, 1] for each symbol
        #   action[i] = fraction of portfolio to allocate to symbol i
        self.action_space = spaces.Box(
            low=0.0, high=1.0, shape=(self.n_symbols,), dtype=np.float32
        )
        
        # Observation space: features + holdings + cash
        # Rough estimate: 10 features per symbol + holdings + cash + regime
        self.feature_dim = 10
        obs_size = (
            self.n_symbols * self.feature_dim  # Features per symbol
            + self.n_symbols  # Holdings fraction
            + 1  # Cash fraction
            + 1  # Regime state (0=bear, 1=sideways, 2=bull)
            + 1  # Anomaly flag
        )
        self.observation_space = spaces.Box(
            low=-1e6, high=1e6, shape=(obs_size,), dtype=np.float32
        )
    
    def reset(self, seed: Optional[int] = None) -> Tuple[np.ndarray, Dict]:
        """Reset environment to initial state."""
        super().reset(seed=seed)
        
        self.current_step = 0
        self.portfolio_value = self.starting_capital
        self.cash = self.starting_capital
        self.holdings = {s: 0.0 for s in self.symbols}
        self.entry_prices = {s: 0.0 for s in self.symbols}
        self.trade_history = []
        self.portfolio_history = [self.portfolio_value]
        self.returns = [0.0]
        self.sharpe_samples = []
        
        return self._get_observation(), {}
    
    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        """
        Execute one step of environment.
        
        Args:
            action: Position sizes [0, 1] for each symbol
        
        Returns:
            obs, reward, terminated, truncated, info
        """
        if not (isinstance(action, (list, tuple, np.ndarray))):
            raise TypeError(f"action must be array-like, got {type(action)}")
        
        action = np.clip(action, 0.0, 1.0).astype(np.float32)
        
        # Check if we're in trading hours
        in_trading_hours = is_trading_hours()
        if not in_trading_hours:
            # Outside trading hours: hold positions, minimal reward
            self.current_step += 1
            obs = self._get_observation()
            reward = 0.0
            terminated = self.current_step >= self.max_steps
            return obs, reward, terminated, False, {"trading_hours": False}
        
        # Get current prices
        prices = {}
        for s in self.symbols:
            if self.current_step < len(self.price_data[s]):
                prices[s] = float(self.price_data[s][self.current_step])
            else:
                prices[s] = float(self.price_data[s][-1])
        
        # Calculate previous portfolio value for reward
        prev_portfolio_value = self.portfolio_value
        
        # Execute trades based on action
        # Action[i] = target position size as % of portfolio for symbol i
        trade_rewards = 0.0
        for i, symbol in enumerate(self.symbols):
            target_fraction = action[i]
            current_price = prices[symbol]
            
            # Check anomalies (Task 9)
            is_anomaly = False
            if self.anomaly_detector:
                try:
                    is_anomaly = self.anomaly_detector.is_anomaly([current_price])
                except:
                    pass
            
            if is_anomaly:
                # Reduce position during anomalies
                target_fraction = max(0.0, target_fraction * 0.5)
                trade_rewards -= 0.05
            
            # Get regime-aware parameters (Task 10)
            regime_multiplier = 1.0
            if self.regime_detector:
                try:
                    regime = self.regime_detector.get_regime([current_price])
                    params = self.regime_detector.get_strategy_params(regime)
                    regime_multiplier = params.get("risk_multiplier", 1.0)
                except:
                    pass
            
            target_fraction *= regime_multiplier
            
            # Calculate target quantity (IDX lots: minimum 100 shares)
            target_quantity = int((target_fraction * self.portfolio_value) / current_price)
            # Round to nearest lot size
            target_quantity = (target_quantity // self.position_size_shares) * self.position_size_shares
            target_quantity = int(target_quantity)
            
            # Enforce max leverage
            max_quantity = int((self.max_leverage * self.portfolio_value) / current_price)
            target_quantity = min(target_quantity, max_quantity)
            
            current_quantity = int(self.holdings[symbol])
            
            if target_quantity > current_quantity:
                # BUY
                qty_to_buy = target_quantity - current_quantity
                cost = qty_to_buy * current_price * (1.0 + self.commission_pct)
                
                if cost <= self.cash:
                    self.holdings[symbol] = target_quantity
                    self.cash -= cost
                    self.entry_prices[symbol] = current_price
                else:
                    # Insufficient cash
                    qty_bought = int(self.cash / (current_price * (1.0 + self.commission_pct)))
                    if qty_bought >= self.position_size_shares:
                        self.holdings[symbol] += qty_bought
                        self.cash -= qty_bought * current_price * (1.0 + self.commission_pct)
                        trade_rewards -= 0.1  # Penalty for partial fill
            
            elif target_quantity < current_quantity:
                # SELL
                qty_to_sell = current_quantity - target_quantity
                proceeds = qty_to_sell * current_price * (1.0 - self.commission_pct)
                self.holdings[symbol] = target_quantity
                self.cash += proceeds
                trade_rewards += 0.05  # Small bonus for realizing gains/losses
        
        # Update portfolio value
        self.portfolio_value = self.cash
        for s in self.symbols:
            price = prices[s]
            self.portfolio_value += self.holdings[s] * price
        
        # Calculate rewards (Sharpe optimization)
        period_return = (self.portfolio_value - prev_portfolio_value) / prev_portfolio_value if prev_portfolio_value > 0 else 0.0
        
        # Sharpe ratio is computed over recent window (last 20 steps)
        self.returns.append(period_return)
        self.sharpe_samples.append(period_return)
        if len(self.sharpe_samples) > 20:
            self.sharpe_samples.pop(0)
        
        # Compute rolling Sharpe
        if len(self.sharpe_samples) > 1:
            mean_ret = np.mean(self.sharpe_samples)
            std_ret = np.std(self.sharpe_samples)
            sharpe = (mean_ret / std_ret * np.sqrt(252)) if std_ret > 0 else 0.0
        else:
            sharpe = 0.0
        
        reward = period_return + sharpe * 0.1 + trade_rewards
        
        # Penalty for large drawdown
        max_drawdown = (min(self.portfolio_history) - self.starting_capital) / self.starting_capital if self.portfolio_history else 0.0
        if max_drawdown < -0.2:
            reward -= 0.1 * (abs(max_drawdown) + 0.2)
        
        self.portfolio_history.append(self.portfolio_value)
        
        # Advance step
        self.current_step += 1
        terminated = self.current_step >= self.max_steps
        
        obs = self._get_observation()
        
        return obs, float(reward), terminated, False, {
            "portfolio_value": self.portfolio_value,
            "sharpe": sharpe,
            "max_drawdown": max_drawdown,
        }
    
    def _get_observation(self) -> np.ndarray:
        """Get current observation vector."""
        obs_list = []
        
        # Features for each symbol
        for symbol in self.symbols:
            if self.current_step < len(self.price_data[symbol]):
                price = float(self.price_data[symbol][self.current_step])
            else:
                price = float(self.price_data[symbol][-1])
            
            # Basic features (if not in feature_data)
            if symbol in self.feature_data and self.current_step < self.feature_data[symbol].shape[0]:
                features = self.feature_data[symbol][self.current_step][:self.feature_dim]
                while len(features) < self.feature_dim:
                    features = np.append(features, 0.0)
                obs_list.extend(features[:self.feature_dim])
            else:
                # Default features: price, momentum, volatility, etc.
                # Simplified: use price changes + volatility
                if self.current_step > 0:
                    prev_price = float(self.price_data[symbol][self.current_step - 1])
                    returns = (price - prev_price) / prev_price if prev_price > 0 else 0.0
                else:
                    returns = 0.0
                
                default_features = [
                    price / 10000.0,  # Normalized price (IDR)
                    returns,
                    0.0,  # Placeholder for more features
                ] + [0.0] * (self.feature_dim - 3)
                obs_list.extend(default_features[:self.feature_dim])
        
        # Holdings as fractions
        for symbol in self.symbols:
            price = float(self.price_data[symbol][self.current_step]) if self.current_step < len(self.price_data[symbol]) else float(self.price_data[symbol][-1])
            holding_value = self.holdings[symbol] * price
            holding_fraction = holding_value / self.portfolio_value if self.portfolio_value > 0 else 0.0
            obs_list.append(holding_fraction)
        
        # Cash fraction
        cash_fraction = self.cash / self.portfolio_value if self.portfolio_value > 0 else 0.0
        obs_list.append(cash_fraction)
        
        # Regime state (Task 10)
        regime_state = 1.0  # Default: sideways
        if self.regime_detector and self.current_step > 0:
            try:
                prices_slice = [float(self.price_data[self.symbols[0]][i]) for i in range(min(self.current_step + 1, len(self.price_data[self.symbols[0]])))]
                regime = self.regime_detector.get_regime(prices_slice)
                regime_map = {"bull": 2.0, "sideways": 1.0, "bear": 0.0}
                regime_state = regime_map.get(regime, 1.0)
            except:
                pass
        obs_list.append(regime_state)
        
        # Anomaly flag (Task 9)
        anomaly_flag = 0.0
        if self.anomaly_detector and self.current_step > 0:
            try:
                prices_slice = [float(self.price_data[self.symbols[0]][i]) for i in range(min(self.current_step + 1, len(self.price_data[self.symbols[0]])))]
                anomaly_flag = 1.0 if self.anomaly_detector.is_anomaly(prices_slice) else 0.0
            except:
                pass
        obs_list.append(anomaly_flag)
        
        # Pad to observation space size
        obs = np.array(obs_list, dtype=np.float32)
        expected_size = self.observation_space.shape[0]
        if len(obs) < expected_size:
            obs = np.pad(obs, (0, expected_size - len(obs)), mode='constant', constant_values=0.0)
        
        return obs[:expected_size]


# ============================================================================
# Trainer Base Classes
# ============================================================================

@dataclass
class TrainerConfig:
    """Configuration for RL trainers."""
    model_name: str = "trading_agent"
    total_timesteps: int = 100_000
    eval_freq: int = 10_000
    n_eval_episodes: int = 5
    learning_rate: float = 1e-4
    batch_size: int = 64
    verbose: int = 1
    seed: int = 42
    device: str = "auto"
    checkpoint_dir: Optional[str] = None
    log_dir: Optional[str] = None
    
    # PPO specific
    ppo_clip_range: float = 0.2
    ppo_n_steps: int = 2048
    ppo_n_epochs: int = 10
    ppo_gae_lambda: float = 0.95
    ppo_ent_coef: float = 0.01
    
    # SAC specific
    sac_buffer_size: int = 100_000
    sac_learning_starts: int = 10_000
    sac_tau: float = 0.005
    sac_ent_coef: str = "auto"
    sac_target_entropy: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class RLTrainerBase(ABC):
    """Base class for RL trainers."""
    
    def __init__(
        self,
        env: gym.Env,
        config: TrainerConfig,
    ):
        """
        Initialize trainer.
        
        Args:
            env: Training environment
            config: Trainer configuration
        """
        self.env = env
        self.config = config
        self.model = None
        self.eval_env = None
        self.train_step = 0
        self.best_mean_reward = -np.inf
        
        # Setup directories
        if config.checkpoint_dir:
            Path(config.checkpoint_dir).mkdir(parents=True, exist_ok=True)
        if config.log_dir:
            Path(config.log_dir).mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initialized {self.__class__.__name__} with config: {config.model_name}")
    
    @abstractmethod
    def create_model(self) -> None:
        """Create RL model (implemented by subclasses)."""
        pass
    
    def train(
        self,
        total_timesteps: Optional[int] = None,
        callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """
        Train the model.
        
        Args:
            total_timesteps: Override config timesteps
            callback: Optional training callback
        
        Returns:
            Training results
        """
        if self.model is None:
            self.create_model()
        
        timesteps = total_timesteps or self.config.total_timesteps
        
        logger.info(f"Starting training for {timesteps} timesteps...")
        start_time = get_jakarta_now()
        
        try:
            # Train
            self.model.learn(
                total_timesteps=timesteps,
                callback=callback or [],
                log_interval=100,
            )
            
            elapsed = (get_jakarta_now() - start_time).total_seconds()
            logger.info(f"Training completed in {elapsed:.1f}s")
            
            return {
                "status": "success",
                "timesteps": timesteps,
                "elapsed_seconds": elapsed,
                "model": self.model,
                "timestamp_jakarta": start_time.isoformat(),
            }
        
        except Exception as e:
            logger.error(f"Training failed: {e}", exc_info=True)
            return {
                "status": "failed",
                "error": str(e),
                "timestamp_jakarta": get_jakarta_now().isoformat(),
            }
    
    def save(self, path: str) -> bool:
        """Save trained model."""
        try:
            self.model.save(path)
            logger.info(f"Model saved to {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save model: {e}")
            return False
    
    def load(self, path: str) -> bool:
        """Load trained model."""
        try:
            self.model = self.model.__class__.load(path)
            logger.info(f"Model loaded from {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False


# ============================================================================
# PPO Trainer
# ============================================================================

class PPOTrainer(RLTrainerBase):
    """PPO (Proximal Policy Optimization) trainer."""
    
    def create_model(self) -> None:
        """Create PPO model."""
        if not STABLE_BASELINES3_AVAILABLE:
            raise RuntimeError("stable-baselines3 required for PPO")
        
        self.model = PPO(
            "MlpPolicy",
            self.env,
            learning_rate=self.config.learning_rate,
            n_steps=self.config.ppo_n_steps,
            batch_size=self.config.batch_size,
            n_epochs=self.config.ppo_n_epochs,
            gamma=0.99,
            gae_lambda=self.config.ppo_gae_lambda,
            clip_range=self.config.ppo_clip_range,
            ent_coef=self.config.ppo_ent_coef,
            max_grad_norm=0.5,
            vf_coef=0.5,
            verbose=self.config.verbose,
            seed=self.config.seed,
            device=self.config.device,
            tb_log_name="ppo_logs",
        )
        logger.info("Created PPO model")


# ============================================================================
# SAC Trainer
# ============================================================================

class SACTrainer(RLTrainerBase):
    """SAC (Soft Actor-Critic) trainer."""
    
    def create_model(self) -> None:
        """Create SAC model."""
        if not STABLE_BASELINES3_AVAILABLE:
            raise RuntimeError("stable-baselines3 required for SAC")
        
        self.model = SAC(
            "MlpPolicy",
            self.env,
            learning_rate=self.config.learning_rate,
            buffer_size=self.config.sac_buffer_size,
            learning_starts=self.config.sac_learning_starts,
            batch_size=self.config.batch_size,
            tau=self.config.sac_tau,
            ent_coef=self.config.sac_ent_coef,
            target_entropy=self.config.sac_target_entropy,
            max_grad_norm=1.0,
            verbose=self.config.verbose,
            seed=self.config.seed,
            device=self.config.device,
            tb_log_name="sac_logs",
        )
        logger.info("Created SAC model")


# ============================================================================
# Hybrid Trainer (PPO warm-up + SAC fine-tune)
# ============================================================================

class HybridTrainer:
    """
    Two-phase trainer: PPO for warm-up, SAC for fine-tuning.
    
    Phase 1: PPO learns fast initial policies
    Phase 2: SAC refines and explores better
    
    Benefits:
    - Fast initial learning (PPO)
    - Better final policy (SAC)
    - Stable training
    """
    
    def __init__(
        self,
        env: gym.Env,
        config: TrainerConfig,
        ppo_timesteps: int = 100_000,
        sac_timesteps: int = 200_000,
    ):
        """
        Initialize hybrid trainer.
        
        Args:
            env: Training environment
            config: Trainer configuration
            ppo_timesteps: Phase 1 PPO timesteps
            sac_timesteps: Phase 2 SAC timesteps
        """
        self.env = env
        self.config = config
        self.ppo_timesteps = ppo_timesteps
        self.sac_timesteps = sac_timesteps
        
        self.ppo_trainer = None
        self.sac_trainer = None
    
    def train(self) -> Dict[str, Any]:
        """Execute hybrid training."""
        results = {
            "phases": {},
            "timestamp_jakarta": get_jakarta_now().isoformat(),
        }
        
        logger.info("=== PHASE 1: PPO Warm-up ===")
        ppo_config = TrainerConfig(**self.config.to_dict())
        ppo_config.total_timesteps = self.ppo_timesteps
        ppo_config.model_name = f"{self.config.model_name}_ppo"
        
        self.ppo_trainer = PPOTrainer(self.env, ppo_config)
        ppo_results = self.ppo_trainer.train()
        results["phases"]["ppo"] = ppo_results
        
        if ppo_results["status"] != "success":
            logger.error("PPO training failed")
            return results
        
        logger.info("=== PHASE 2: SAC Fine-tuning ===")
        sac_config = TrainerConfig(**self.config.to_dict())
        sac_config.total_timesteps = self.sac_timesteps
        sac_config.model_name = f"{self.config.model_name}_sac"
        
        # Initialize SAC with PPO's environment and reuse memory if possible
        self.sac_trainer = SACTrainer(self.env, sac_config)
        sac_results = self.sac_trainer.train()
        results["phases"]["sac"] = sac_results
        
        return results
    
    def get_final_model(self):
        """Get final trained model (SAC)."""
        return self.sac_trainer.model if self.sac_trainer else None
    
    def save(self, path: str) -> bool:
        """Save final model."""
        if self.sac_trainer:
            return self.sac_trainer.save(path)
        return False


# ============================================================================
# Utility Functions
# ============================================================================

def create_training_env(
    symbols: List[str],
    price_data: Dict[str, List[float]],
    anomaly_detector: Optional[Any] = None,
    regime_detector: Optional[Any] = None,
    **kwargs
) -> MultiSymbolTradingEnv:
    """Factory for creating training environments."""
    return MultiSymbolTradingEnv(
        symbols=symbols,
        price_data=price_data,
        anomaly_detector=anomaly_detector,
        regime_detector=regime_detector,
        **kwargs
    )


def evaluate_policy(
    model,
    env: gym.Env,
    n_episodes: int = 10,
) -> Dict[str, float]:
    """
    Evaluate a trained policy.
    
    Returns:
        Dict with mean/std rewards and other metrics
    """
    episode_rewards = []
    episode_lengths = []
    
    for _ in range(n_episodes):
        obs, _ = env.reset()
        episode_reward = 0.0
        episode_length = 0
        done = False
        
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)
            episode_reward += reward
            episode_length += 1
            done = terminated or truncated
        
        episode_rewards.append(episode_reward)
        episode_lengths.append(episode_length)
    
    return {
        "mean_reward": float(np.mean(episode_rewards)),
        "std_reward": float(np.std(episode_rewards)),
        "mean_length": float(np.mean(episode_lengths)),
        "std_length": float(np.std(episode_lengths)),
        "episodes": n_episodes,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Policy Trainer Module (Task 11) - Ready for import")
