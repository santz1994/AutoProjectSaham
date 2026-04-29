"""Fase 4: Deep RL Training Script for Crypto/Forex.

End-to-end training pipeline that:
1. Loads pre-computed feature dataset (from scripts/prepare_data.py)
2. Builds price series + volume series for TradingEnv
3. Wraps TradingEnv in a Gymnasium-compatible wrapper for SB3
4. Trains PPO (or SAC) with checkpoints, TensorBoard, and evaluation
5. Supports resuming from checkpoints for Kaggle 12-hour sessions
6. Exports final model brain for live deployment

Usage (local):
  python scripts/train_crypto_rl.py \
      --dataset data/dataset/hf_BTCUSDT_5m_features.csv \
      --symbol BTC/USDT --timesteps 500000

Usage (Kaggle resume):
  python scripts/train_crypto_rl.py \
      --dataset data/dataset/hf_BTCUSDT_5m_features.csv \
      --resume models/checkpoints/rl_ckpt_100000_steps.zip \
      --timesteps 500000
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _set_seeds(seed: int) -> None:
    """Set all RNG seeds for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    except ImportError:
        pass


def _load_dataset(path: str) -> pd.DataFrame:
    """Load feature dataset (CSV or Parquet)."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Dataset not found: {path}")

    if path.lower().endswith(".parquet"):
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)

    if "close" not in df.columns and "last_price" in df.columns:
        df["close"] = df["last_price"]

    if "close" not in df.columns:
        raise ValueError("Dataset must contain 'close' or 'last_price' column")

    return df


def _extract_price_volume(df: pd.DataFrame) -> Tuple[List[float], List[float]]:
    """Extract price and volume series from feature DataFrame."""
    prices = df["close"].astype(float).tolist()
    volumes = df["volume"].astype(float).tolist() if "volume" in df.columns else [0.0] * len(prices)
    return prices, volumes


# ---------------------------------------------------------------------------
# Gymnasium-compatible wrapper for SB3
# ---------------------------------------------------------------------------

try:
    import gymnasium as gym  # type: ignore[import-untyped]
    _GYM_BASE = gym.Env
except ImportError:
    try:
        import gym  # type: ignore[import-untyped]
        _GYM_BASE = gym.Env
    except ImportError:
        # Fallback: use object (SB3 won't accept it but at least import won't crash)
        _GYM_BASE = object


class SB3TradingEnvWrapper(_GYM_BASE):  # type: ignore[misc]
    """Wrap TradingEnv to be fully compatible with Stable-Baselines3.

    Inherits from gymnasium.Env so SB3 DummyVecEnv accepts it.
    Handles both Gym and Gymnasium reset/step signatures.

    ``action_mode`` controls whether the wrapper exposes a discrete
    (MultiDiscrete) action space for PPO/A2C or a continuous (Box)
    action space for SAC/TD3.  Continuous actions in [-1, 1] are mapped
    to discrete TradingEnv actions:
        < -0.33 → sell (2), between → hold (0), > 0.33 → buy (1)
    """

    def __init__(
        self,
        prices: List[float],
        volumes: Optional[List[float]] = None,
        symbol: str = "BTC/USDT",
        starting_cash: float = 10_000.0,
        position_size: float = 0.001,
        commission_pct: float = 0.001,
        slippage_pct: float = 0.0005,
        max_leverage: float = 20.0,
        maintenance_margin_fraction: float = 0.10,
        sharpe_lookback: int = 50,
        action_mode: str = "discrete",
    ):
        super().__init__()
        from src.rl.envs.trading_env import TradingEnv

        self.inner = TradingEnv(
            prices=prices,
            volumes=volumes,
            symbol=symbol,
            starting_cash=starting_cash,
            position_size=position_size,
            commission_pct=commission_pct,
            slippage_pct=slippage_pct,
            max_leverage=max_leverage,
            maintenance_margin_fraction=maintenance_margin_fraction,
            sharpe_lookback=sharpe_lookback,
        )
        self._action_mode = action_mode

        # Expose spaces for SB3 (required by gymnasium.Env)
        if _GYM_BASE is not object:
            if action_mode == "continuous":
                # Continuous action space for SAC/TD3: single float in [-1, 1]
                self.action_space = gym.spaces.Box(
                    low=-1.0, high=1.0, shape=(1,), dtype=np.float32
                )
            else:
                # Discrete action space for PPO/A2C
                self.action_space = getattr(
                    self.inner, "action_space",
                    gym.spaces.MultiDiscrete([4, 5]),
                )
            obs_shape = getattr(self.inner, "observation_shape", (8,))
            self.observation_space = getattr(
                self.inner, "observation_space",
                gym.spaces.Box(low=-1e9, high=1e9, shape=obs_shape, dtype=np.float32),
            )

    def _map_continuous_action(self, action) -> int:
        """Map continuous action [-1, 1] to discrete TradingEnv action."""
        val = float(np.asarray(action).flatten()[0])
        if val < -0.33:
            return 2   # sell
        elif val > 0.33:
            return 1   # buy
        else:
            return 0   # hold

    def reset(self, *, seed: Optional[int] = None, options: Optional[dict] = None):
        out = self.inner.reset(0)
        if isinstance(out, tuple):
            return out[0], {}
        return out, {}

    def step(self, action):
        if self._action_mode == "continuous":
            action = self._map_continuous_action(action)
        out = self.inner.step(action)
        if len(out) == 5:
            # gymnasium: obs, reward, terminated, truncated, info
            obs, reward, terminated, truncated, info = out
            return obs, float(reward), bool(terminated), bool(truncated), info
        elif len(out) == 4:
            # old gym: obs, reward, done, info
            obs, reward, done, info = out
            return obs, float(reward), bool(done), False, info
        else:
            raise RuntimeError(f"Unexpected step return shape: {len(out)}")

    def render(self):
        if hasattr(self.inner, "render"):
            self.inner.render()

    def close(self):
        pass


# ---------------------------------------------------------------------------
# Custom SB3 Callbacks
# ---------------------------------------------------------------------------

def _make_callbacks(
    checkpoint_dir: str,
    checkpoint_freq: int,
    eval_env,
    tensorboard_log: str,
    total_timesteps: int,
    wandb_enabled: bool = False,
    wandb_project: str = "autosaham-rl",
):
    """Build SB3 callback list."""
    from stable_baselines3.common.callbacks import (
        CallbackList,
        CheckpointCallback,
        EvalCallback,
    )

    cbs = []

    # Checkpoint every N steps
    cp_freq = checkpoint_freq if checkpoint_freq > 0 else max(1, total_timesteps // 20)
    cbs.append(
        CheckpointCallback(
            save_freq=cp_freq,
            save_path=checkpoint_dir,
            name_prefix="rl_ckpt",
            save_replay_buffer=True,
            save_vecnormalize=True,
        )
    )

    # Eval callback
    eval_freq = max(1, total_timesteps // 10)
    cbs.append(
        EvalCallback(
            eval_env,
            best_model_save_path=checkpoint_dir,
            log_path=tensorboard_log,
            eval_freq=eval_freq,
            n_eval_episodes=5,
            deterministic=True,
            render=False,
        )
    )

    # Optional W&B
    if wandb_enabled:
        try:
            import wandb
            from wandb.integration.sb3 import WandbCallback

            wandb.init(
                project=wandb_project,
                config={"total_timesteps": total_timesteps},
                reinit=True,
                sync_tensorboard=True,
            )
            cbs.append(WandbCallback(verbose=1))
            print("[W&B] Logging enabled")
        except Exception as e:
            print(f"[W&B] Init failed (continuing without): {e}")

    return CallbackList(cbs)


# ---------------------------------------------------------------------------
# Main Training Pipeline
# ---------------------------------------------------------------------------

def train(
    dataset_path: str,
    symbol: str = "BTC/USDT",
    total_timesteps: int = 500_000,
    algorithm: str = "ppo",
    learning_rate: float = 3e-4,
    n_steps: int = 2048,
    batch_size: int = 64,
    n_epochs: int = 10,
    gamma: float = 0.99,
    gae_lambda: float = 0.95,
    clip_range: float = 0.2,
    ent_coef: float = 0.01,
    vf_coef: float = 0.5,
    max_grad_norm: float = 0.5,
    starting_cash: float = 10_000.0,
    position_size: float = 0.001,
    commission_pct: float = 0.001,
    slippage_pct: float = 0.0005,
    max_leverage: float = 20.0,
    maintenance_margin_fraction: float = 0.10,
    sharpe_lookback: int = 50,
    checkpoint_dir: str = "models/checkpoints",
    checkpoint_freq: int = 10_000,
    model_out: str = "models/crypto_sniper_v1_final.zip",
    tensorboard_log: str = "models/rl_tb",
    resume_path: Optional[str] = None,
    seed: Optional[int] = None,
    device: str = "auto",
    wandb_enabled: bool = False,
    wandb_project: str = "autosaham-rl",
    train_split: float = 0.85,
) -> Dict[str, Any]:
    """Execute full Fase 4 training pipeline.

    Args:
        dataset_path: Path to feature CSV/Parquet from prepare_data pipeline
        symbol: Trading symbol
        total_timesteps: Total training timesteps (accumulate across resumes)
        algorithm: "ppo" or "sac"
        learning_rate: Learning rate
        n_steps: PPO rollout buffer size
        batch_size: Minibatch size
        n_epochs: PPO epochs per update
        gamma: Discount factor
        gae_lambda: GAE lambda
        clip_range: PPO clip range
        ent_coef: Entropy coefficient
        vf_coef: Value function coefficient
        max_grad_norm: Max gradient norm
        starting_cash: Starting cash for env
        position_size: Position size per trade
        commission_pct: Trading fee percentage
        slippage_pct: Slippage percentage
        max_leverage: Maximum leverage
        maintenance_margin_fraction: Liquidation threshold fraction
        sharpe_lookback: Rolling window for Sharpe computation
        checkpoint_dir: Directory to save checkpoints
        checkpoint_freq: Save checkpoint every N steps
        model_out: Final model output path
        tensorboard_log: TensorBoard log directory
        resume_path: Path to checkpoint to resume from
        seed: Random seed
        device: "auto", "cpu", "cuda", "cuda:0", etc.
        wandb_enabled: Enable W&B logging
        wandb_project: W&B project name
        train_split: Fraction of data for training (rest for eval)

    Returns:
        Training summary dict
    """
    # Seeds
    if seed is None:
        seed = random.randint(0, 2**31 - 1)
    _set_seeds(int(seed))

    # Load dataset
    print(f"[Fase4] Loading dataset: {dataset_path}")
    df = _load_dataset(dataset_path)
    prices, volumes = _extract_price_volume(df)
    print(f"[Fase4] Loaded {len(prices)} candles for {symbol}")

    # Train/eval split
    split_idx = int(len(prices) * train_split)
    if split_idx < 100:
        raise ValueError(f"Dataset too small for training: {len(prices)} rows")

    train_prices = prices[:split_idx]
    train_volumes = volumes[:split_idx]
    eval_prices = prices[split_idx:]
    eval_volumes = volumes[split_idx:]

    print(f"[Fase4] Train: {len(train_prices)} candles, Eval: {len(eval_prices)} candles")

    # Environment factory
    def make_train_env():
        def _init():
            return SB3TradingEnvWrapper(
                prices=train_prices,
                volumes=train_volumes,
                symbol=symbol,
                starting_cash=starting_cash,
                position_size=position_size,
                commission_pct=commission_pct,
                slippage_pct=slippage_pct,
                max_leverage=max_leverage,
                maintenance_margin_fraction=maintenance_margin_fraction,
                sharpe_lookback=sharpe_lookback,
            )
        return _init

    def make_eval_env():
        def _init():
            return SB3TradingEnvWrapper(
                prices=eval_prices,
                volumes=eval_volumes,
                symbol=symbol,
                starting_cash=starting_cash,
                position_size=position_size,
                commission_pct=commission_pct,
                slippage_pct=slippage_pct,
                max_leverage=max_leverage,
                maintenance_margin_fraction=maintenance_margin_fraction,
                sharpe_lookback=sharpe_lookback,
            )
        return _init

    # SB3 imports
    from stable_baselines3 import PPO, SAC
    from stable_baselines3.common.vec_env import DummyVecEnv

    # Prepare vectorized envs
    vec_env = DummyVecEnv([make_train_env()])
    eval_vec_env = DummyVecEnv([make_eval_env()])

    # Ensure directories
    os.makedirs(checkpoint_dir, exist_ok=True)
    os.makedirs(tensorboard_log, exist_ok=True)
    os.makedirs(os.path.dirname(model_out) or ".", exist_ok=True)

    # Resume or create new model
    algo_cls = PPO if algorithm.lower() == "ppo" else SAC

    if resume_path and os.path.exists(resume_path):
        print(f"[Fase4] Resuming from checkpoint: {resume_path}")
        model = algo_cls.load(
            resume_path,
            env=vec_env,
            device=device,
            custom_objects={
                "learning_rate": learning_rate,
                "n_steps": n_steps if algorithm.lower() == "ppo" else None,
            },
        )
        # Reset timestep counter to accumulate
        model.num_timesteps = 0
    else:
        print(f"[Fase4] Creating new {algorithm.upper()} model")
        if algorithm.lower() == "ppo":
            model = PPO(
                "MlpPolicy",
                vec_env,
                learning_rate=learning_rate,
                n_steps=n_steps,
                batch_size=batch_size,
                n_epochs=n_epochs,
                gamma=gamma,
                gae_lambda=gae_lambda,
                clip_range=clip_range,
                ent_coef=ent_coef,
                vf_coef=vf_coef,
                max_grad_norm=max_grad_norm,
                verbose=1,
                seed=int(seed),
                device=device,
                tensorboard_log=tensorboard_log,
            )
        else:
            model = SAC(
                "MlpPolicy",
                vec_env,
                learning_rate=learning_rate,
                batch_size=batch_size,
                gamma=gamma,
                ent_coef=ent_coef,
                verbose=1,
                seed=int(seed),
                device=device,
                tensorboard_log=tensorboard_log,
            )

    # Save training config
    config = {
        "algorithm": algorithm,
        "symbol": symbol,
        "total_timesteps": total_timesteps,
        "learning_rate": learning_rate,
        "n_steps": n_steps,
        "batch_size": batch_size,
        "n_epochs": n_epochs,
        "gamma": gamma,
        "gae_lambda": gae_lambda,
        "clip_range": clip_range,
        "ent_coef": ent_coef,
        "vf_coef": vf_coef,
        "max_grad_norm": max_grad_norm,
        "starting_cash": starting_cash,
        "position_size": position_size,
        "commission_pct": commission_pct,
        "slippage_pct": slippage_pct,
        "max_leverage": max_leverage,
        "maintenance_margin_fraction": maintenance_margin_fraction,
        "sharpe_lookback": sharpe_lookback,
        "dataset_path": dataset_path,
        "dataset_rows": len(prices),
        "train_rows": len(train_prices),
        "eval_rows": len(eval_prices),
        "seed": int(seed),
        "device": device,
        "resume_path": resume_path,
    }

    config_path = os.path.splitext(model_out)[0] + "_config.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    print(f"[Fase4] Saved config to {config_path}")

    # Build callbacks
    callbacks = _make_callbacks(
        checkpoint_dir=checkpoint_dir,
        checkpoint_freq=checkpoint_freq,
        eval_env=eval_vec_env,
        tensorboard_log=tensorboard_log,
        total_timesteps=total_timesteps,
        wandb_enabled=wandb_enabled,
        wandb_project=wandb_project,
    )

    # TRAIN
    print(f"[Fase4] Training {algorithm.upper()} for {total_timesteps:,} timesteps...")
    print(f"[Fase4] Leverage: {max_leverage}x | Commission: {commission_pct*100:.2f}%")
    print(f"[Fase4] Slippage: {slippage_pct*100:.3f}% | Death Penalty: {maintenance_margin_fraction*100:.0f}%")
    print(f"[Fase4] TensorBoard: {tensorboard_log}")
    print(f"[Fase4] Device: {model.device}")

    model.learn(
        total_timesteps=total_timesteps,
        callback=callbacks,
        progress_bar=True,
    )

    # Save final model
    model.save(model_out)
    print(f"[Fase4] Saved final model to {model_out}")

    # Final evaluation
    from stable_baselines3.common.evaluation import evaluate_policy

    mean_reward, std_reward = evaluate_policy(
        model, eval_vec_env, n_eval_episodes=10, deterministic=True,
    )
    print(f"[Fase4] Final evaluation: mean_reward={mean_reward:.3f} +/- {std_reward:.3f}")

    # Save training summary
    summary = {
        "model_path": model_out,
        "config_path": config_path,
        "algorithm": algorithm,
        "symbol": symbol,
        "total_timesteps": total_timesteps,
        "final_mean_reward": float(mean_reward),
        "final_std_reward": float(std_reward),
        "dataset_rows": len(prices),
        "train_rows": len(train_prices),
        "eval_rows": len(eval_prices),
        "max_leverage": max_leverage,
        "seed": int(seed),
        "device": str(model.device),
    }

    summary_path = os.path.splitext(model_out)[0] + "_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"[Fase4] Saved summary to {summary_path}")

    # Cleanup
    vec_env.close()
    eval_vec_env.close()

    # Close W&B if active
    try:
        import wandb
        if wandb.run is not None:
            wandb.finish()
    except Exception:
        pass

    return summary


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Fase 4: Deep RL Training for Crypto/Forex (AutoSaham)"
    )

    # Data
    parser.add_argument(
        "--dataset", required=True,
        help="Path to feature dataset CSV/Parquet (from scripts/prepare_data.py)",
    )
    parser.add_argument("--symbol", default="BTC/USDT", help="Trading symbol")

    # Training
    parser.add_argument("--timesteps", type=int, default=500_000, help="Total training timesteps")
    parser.add_argument("--algorithm", default="ppo", choices=["ppo", "sac"], help="RL algorithm")
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--n-steps", type=int, default=2048, help="PPO rollout buffer size")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--n-epochs", type=int, default=10, help="PPO epochs per update")
    parser.add_argument("--gamma", type=float, default=0.99)
    parser.add_argument("--gae-lambda", type=float, default=0.95)
    parser.add_argument("--clip-range", type=float, default=0.2)
    parser.add_argument("--ent-coef", type=float, default=0.01)
    parser.add_argument("--vf-coef", type=float, default=0.5)
    parser.add_argument("--max-grad-norm", type=float, default=0.5)

    # Environment
    parser.add_argument("--starting-cash", type=float, default=10_000.0)
    parser.add_argument("--position-size", type=float, default=0.001, help="Position size per trade")
    parser.add_argument("--commission-pct", type=float, default=0.001, help="Trading fee (0.001 = 0.1%)")
    parser.add_argument("--slippage-pct", type=float, default=0.0005, help="Slippage (0.0005 = 0.05%)")
    parser.add_argument("--max-leverage", type=float, default=20.0, help="Maximum leverage")
    parser.add_argument("--maintenance-margin", type=float, default=0.10, help="Liquidation threshold fraction")
    parser.add_argument("--sharpe-lookback", type=int, default=50, help="Rolling Sharpe window")

    # Output
    parser.add_argument("--checkpoint-dir", default="models/checkpoints", help="Checkpoint directory")
    parser.add_argument("--checkpoint-freq", type=int, default=10_000, help="Checkpoint save frequency")
    parser.add_argument("--model-out", default="models/crypto_sniper_v1_final.zip", help="Final model path")
    parser.add_argument("--tensorboard-log", default="models/rl_tb", help="TensorBoard log dir")

    # Resume
    parser.add_argument("--resume", default=None, help="Resume from checkpoint .zip")

    # Misc
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument("--device", default="auto", help="Device: auto/cpu/cuda/cuda:0")
    parser.add_argument("--wandb", action="store_true", help="Enable W&B logging")
    parser.add_argument("--wandb-project", default="autosaham-rl")
    parser.add_argument("--train-split", type=float, default=0.85, help="Train/eval split ratio")

    args = parser.parse_args(argv)

    summary = train(
        dataset_path=args.dataset,
        symbol=args.symbol,
        total_timesteps=args.timesteps,
        algorithm=args.algorithm,
        learning_rate=args.learning_rate,
        n_steps=args.n_steps,
        batch_size=args.batch_size,
        n_epochs=args.n_epochs,
        gamma=args.gamma,
        gae_lambda=args.gae_lambda,
        clip_range=args.clip_range,
        ent_coef=args.ent_coef,
        vf_coef=args.vf_coef,
        max_grad_norm=args.max_grad_norm,
        starting_cash=args.starting_cash,
        position_size=args.position_size,
        commission_pct=args.commission_pct,
        slippage_pct=args.slippage_pct,
        max_leverage=args.max_leverage,
        maintenance_margin_fraction=args.maintenance_margin,
        sharpe_lookback=args.sharpe_lookback,
        checkpoint_dir=args.checkpoint_dir,
        checkpoint_freq=args.checkpoint_freq,
        model_out=args.model_out,
        tensorboard_log=args.tensorboard_log,
        resume_path=args.resume,
        seed=args.seed,
        device=args.device,
        wandb_enabled=args.wandb,
        wandb_project=args.wandb_project,
        train_split=args.train_split,
    )

    print("\n" + "=" * 60)
    print("Fase 4 Training Complete!")
    print(f"  Model: {summary['model_path']}")
    print(f"  Mean Reward: {summary['final_mean_reward']:.3f} +/- {summary['final_std_reward']:.3f}")
    print(f"  Timesteps: {summary['total_timesteps']:,}")
    print(f"  Leverage: {summary['max_leverage']}x")
    print("=" * 60)

    return summary


if __name__ == "__main__":
    main()