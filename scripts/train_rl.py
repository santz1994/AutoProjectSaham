"""RL training demo using the project's TradingEnv.

This script will attempt to use `stable_baselines3` + `gym`/`gymnasium` to
train a PPO policy. If `stable_baselines3` is not installed the script will
fall back to running a small random-agent demo so the environment can be
validated without heavy dependencies.

Usage:
  python bin/runner.py scripts/train_rl.py -- --symbol DEMO --timesteps 1000
"""
from __future__ import annotations

import argparse
import json
import os
import random
from typing import Any, Tuple

import numpy as np

from src.demo import generate_price_series
from src.rl.envs.trading_env import TradingEnv


class GymWrapper:
    """Wrap the project's TradingEnv to a gym-like Env compatible with SB3.

    Provides the minimal API: `reset()` and `step(action)` returning
    (obs, reward, done, info). It exposes `action_space` and `observation_space`
    if `gym` is installed; otherwise they're set to None.
    """

    def __init__(self, prices: list[float]):
        self.inner = TradingEnv(prices=prices, symbol="RL")
        # try to adapt spaces if gymnasium/gym is available
        try:
            import gym

            # prefer the inner env's action_space if available
            self.action_space = getattr(
                self.inner,
                "action_space",
                gym.spaces.MultiDiscrete([4, 5]),
            )
            obs_shape = getattr(self.inner, "observation_shape", (8,))
            self.observation_space = getattr(
                self.inner,
                "observation_space",
                gym.spaces.Box(low=-1e9, high=1e9, shape=obs_shape, dtype=np.float32),
            )
        except Exception:
            self.action_space = None
            self.observation_space = None

    def reset(self) -> Any:
        out = self.inner.reset(0)
        # normalize Gym / Gymnasium reset signatures: return observation only for SB3
        if isinstance(out, (tuple, list)):
            return out[0]
        return out

    def step(self, action) -> Tuple[Any, float, bool, dict]:
        # pass action through to inner env; it accepts scalar or array-like
        out = self.inner.step(action)
        # TradingEnv.step returns either (obs, reward, done, info) or
        # (obs, reward, terminated, truncated, info) depending on gym availability.
        if len(out) == 4:
            obs, reward, done, info = out
            return obs, reward, done, info
        elif len(out) == 5:
            obs, reward, terminated, truncated, info = out
            done = bool(terminated or truncated)
            return obs, reward, done, info
        else:
            raise RuntimeError("unexpected step return shape")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="DEMO")
    parser.add_argument("--timesteps", type=int, default=2000)
    parser.add_argument("--n", type=int, default=300, help="price series length")
    parser.add_argument("--model-out", default="models/rl_ppo.zip")
    parser.add_argument(
        "--seed", type=int, default=None, help="random seed for reproducibility"
    )
    parser.add_argument(
        "--tensorboard-log", default="models/rl_tb", help="tensorboard log dir"
    )
    parser.add_argument(
        "--checkpoint-freq",
        type=int,
        default=0,
        help="checkpoint save frequency (steps). 0 -> auto",
    )
    parser.add_argument("--policy", default="MlpPolicy")
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--n-steps", type=int, default=2048)
    parser.add_argument("--device", default="auto")
    parser.add_argument(
        "--wandb", action="store_true", help="enable optional Weights & Biases logging"
    )
    parser.add_argument("--wandb-project", default="autosaham-rl")
    args = parser.parse_args(argv)

    # --- seeds & reproducibility ---
    if args.seed is None:
        args.seed = random.randint(0, 2**31 - 1)
    seed = int(args.seed)
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch

        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    except Exception:
        pass

    # generate a demo price series (deterministic given the seed)
    prices = generate_price_series(n=args.n, start_price=100.0, volatility_pct=1.5)

    # factory to create independent env instances (used by SB3 VecEnv)
    def make_env(p=prices):
        def _init():
            return GymWrapper(p)

        return _init

    # persist args/config next to model for reproducibility
    os.makedirs(os.path.dirname(args.model_out) or ".", exist_ok=True)
    cfg_path = os.path.splitext(args.model_out)[0] + "_config.json"
    try:
        with open(cfg_path, "w") as fh:
            json.dump(vars(args), fh, indent=2)
        print("Saved training config to", cfg_path)
    except Exception as e:
        print("Failed to save config:", e)

    # Try to train with stable_baselines3 if available
    try:
        from stable_baselines3 import PPO
        from stable_baselines3.common.callbacks import (
            CallbackList,
            CheckpointCallback,
            EvalCallback,
        )
        from stable_baselines3.common.evaluation import evaluate_policy
        from stable_baselines3.common.vec_env import DummyVecEnv

        # prepare vectorized training and eval envs
        vec_env = DummyVecEnv([make_env()])
        eval_env = DummyVecEnv([make_env()])

        # checkpointing
        if args.checkpoint_freq and args.checkpoint_freq > 0:
            cp_freq = int(args.checkpoint_freq)
        else:
            cp_freq = max(1, int(args.timesteps // 10))
        checkpoint_dir = os.path.dirname(args.model_out) or "."
        checkpoint_cb = CheckpointCallback(
            save_freq=cp_freq,
            save_path=checkpoint_dir,
            name_prefix="rl_ckpt",
        )

        # evaluation callback (logs to tensorboard dir)
        eval_freq = max(1, int(args.timesteps // 10))
        eval_cb = EvalCallback(
            eval_env,
            best_model_save_path=checkpoint_dir,
            log_path=args.tensorboard_log,
            eval_freq=eval_freq,
            deterministic=True,
            render=False,
        )

        # optional Weights & Biases integration
        wb_run = None
        wandb_cb = None
        if args.wandb:
            try:
                import wandb
                from wandb.integration.sb3 import WandbCallback

                wb_run = wandb.init(
                    project=args.wandb_project,
                    config=vars(args),
                    reinit=True,
                    sync_tensorboard=True,
                )
                wandb_cb = WandbCallback(verbose=1)
                print("W&B enabled, logging to project", args.wandb_project)
            except Exception as e:
                print("W&B requested but failed to init:", e)
                wb_run = None
                wandb_cb = None

        cbs = [checkpoint_cb, eval_cb]
        if wandb_cb is not None:
            cbs.append(wandb_cb)
        callbacks = CallbackList(cbs)

        model = PPO(
            args.policy,
            vec_env,
            verbose=1,
            seed=seed,
            tensorboard_log=args.tensorboard_log,
            device=args.device,
            learning_rate=float(args.learning_rate),
            n_steps=int(args.n_steps),
        )

        model.learn(total_timesteps=int(args.timesteps), callback=callbacks)

        model.save(args.model_out)
        print("Saved PPO model to", args.model_out)

        # close W&B run if one was started
        if wb_run is not None:
            try:
                try:
                    wb_run.finish()
                except Exception:
                    # fallback to module-level finish
                    import wandb as _wandb

                    _wandb.finish()
            except Exception:
                pass

        # run a short evaluation
        mean_reward, std_reward = evaluate_policy(model, eval_env, n_eval_episodes=5)
        print(f"Evaluation mean reward: {mean_reward:.3f} +/- {std_reward:.3f}")
        return
    except Exception as e:
        print("stable_baselines3 not available or failed to train:", e)

    # Fallback: run a short random-agent demonstration (deterministic via seed)
    print("Running random-agent demo (no SB3).")
    for ep in range(5):
        # instantiate a single environment per episode (avoid recreating per step)
        env = make_env()()
        reset_out = env.reset()
        obs = reset_out[0] if isinstance(reset_out, (tuple, list)) else reset_out

        total = 0.0
        done = False
        while not done:
            decision = random.choice([0, 1, 2, 3])
            tp = random.choice([0, 1, 2, 3, 4])
            out = env.step([decision, tp])
            # adapt to step return shapes
            if len(out) == 4:
                obs, reward, done, info = out
            else:
                obs, reward, terminated, truncated, info = out
                done = bool(terminated or truncated)
            total += float(reward)
        print(f"Episode {ep+1} reward {total:.2f}")


if __name__ == "__main__":
    main()
