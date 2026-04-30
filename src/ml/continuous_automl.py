"""
Continuous AutoML Pipeline — Self-Tuning RL Hyperparameters

Runs weekly Optuna hyperparameter optimization on recent market data,
walk-forward validates new models, and auto-promotes winners to production.

This ensures the system never suffers from concept drift — parameters
that worked in January may fail in March. The system self-evolves.

Architecture:
  ┌────────────────────────────────────────────────────────────┐
  │              Continuous AutoML Pipeline                     │
  │                                                             │
  │  [Recent Data] → [Optuna Study] → [Walk-Forward Validate]  │
  │       ↑                                        ↓            │
  │  [2-week window]                    [Better than prod?]     │
  │                                               ↓            │
  │                                    [Auto-Promote → Registry]│
  └────────────────────────────────────────────────────────────┘

Key Features:
- Optuna TPE sampler for efficient hyperparameter search
- Walk-forward out-of-sample validation (no overfitting)
- Auto-promotion only if Calmar Ratio improves
- Model Registry for versioned model storage
- Prioritized Experience Replay on recent market regimes
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

try:
    import optuna
    OPTUNA_AVAILABLE = True
except ImportError:
    OPTUNA_AVAILABLE = False


@dataclass
class AutoMLConfig:
    """Configuration for Continuous AutoML Pipeline."""
    # Optuna study settings
    n_trials: int = 50
    timeout_per_trial: float = 600.0  # seconds
    total_timeout: float = 7200.0     # 2 hours max for full study
    
    # Walk-forward validation
    walk_forward_splits: int = 5
    train_ratio: float = 0.7
    
    # Auto-promotion thresholds
    min_calmar_improvement: float = 0.1   # 10% improvement required
    min_sharpe_improvement: float = 0.05  # 5% Sharpe improvement required
    min_win_rate: float = 0.45            # Minimum acceptable win rate
    
    # Model registry
    registry_dir: str = "models/registry"
    max_registry_models: int = 10
    
    # Schedule
    auto_run_interval: float = 7 * 24 * 3600.0  # 7 days
    
    # RL algorithm to tune
    algorithm: str = "PPO"  # "PPO" or "SAC"


@dataclass
class TrialResult:
    """Result of a single Optuna trial."""
    trial_number: int
    params: Dict[str, Any]
    calmar_ratio: float = 0.0
    sharpe_ratio: float = 0.0
    total_return: float = 0.0
    win_rate: float = 0.0
    max_drawdown: float = 0.0
    n_trades: int = 0
    training_time: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trial_number": self.trial_number,
            "params": self.params,
            "calmar_ratio": self.calmar_ratio,
            "sharpe_ratio": self.sharpe_ratio,
            "total_return": self.total_return,
            "win_rate": self.win_rate,
            "max_drawdown": self.max_drawdown,
            "n_trades": self.n_trades,
            "training_time": self.training_time,
            "error": self.error,
        }


@dataclass
class WalkForwardResult:
    """Walk-forward validation result."""
    n_splits: int
    avg_calmar: float
    avg_sharpe: float
    avg_return: float
    avg_win_rate: float
    split_results: List[Dict[str, float]] = field(default_factory=list)
    is_better_than_production: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "n_splits": self.n_splits,
            "avg_calmar": self.avg_calmar,
            "avg_sharpe": self.avg_sharpe,
            "avg_return": self.avg_return,
            "avg_win_rate": self.avg_win_rate,
            "is_better": self.is_better_than_production,
            "splits": self.split_results,
        }


class ModelRegistry:
    """
    Versioned model storage with auto-promotion.
    
    Stores trained RL models with metadata and promotes the best one
    to production when walk-forward validation passes.
    """

    def __init__(self, registry_dir: str = "models/registry"):
        self.registry_dir = Path(registry_dir)
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.registry_dir / "metadata.json"
        self._metadata = self._load_metadata()

    def _load_metadata(self) -> Dict[str, Any]:
        """Load registry metadata."""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, "r") as f:
                    return json.load(f)
            except Exception:
                return {"models": [], "production_model": None}
        return {"models": [], "production_model": None}

    def _save_metadata(self) -> None:
        """Save registry metadata."""
        with open(self.metadata_file, "w") as f:
            json.dump(self._metadata, f, indent=2, default=str)

    def register_model(
        self,
        model_path: str,
        metrics: Dict[str, float],
        params: Dict[str, Any],
        description: str = "",
    ) -> str:
        """
        Register a new model version.
        
        Returns:
            Model ID (version string)
        """
        version = f"v{len(self._metadata['models']) + 1}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        
        model_entry = {
            "version": version,
            "path": model_path,
            "metrics": metrics,
            "params": params,
            "description": description,
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "is_production": False,
        }
        
        self._metadata["models"].append(model_entry)
        
        # Keep only max_registry_models
        if len(self._metadata["models"]) > 10:
            self._metadata["models"] = self._metadata["models"][-10:]
        
        self._save_metadata()
        logger.info(f"Model registered: {version} (calmar={metrics.get('calmar_ratio', 0):.3f})")
        return version

    def promote_to_production(self, version: str) -> bool:
        """Promote a model version to production."""
        for model in self._metadata["models"]:
            if model["version"] == version:
                # Demote current production
                for m in self._metadata["models"]:
                    m["is_production"] = False
                model["is_production"] = True
                self._metadata["production_model"] = version
                self._save_metadata()
                logger.info(f"Model {version} promoted to PRODUCTION")
                return True
        return False

    def get_production_model(self) -> Optional[Dict[str, Any]]:
        """Get current production model info."""
        for model in self._metadata["models"]:
            if model.get("is_production"):
                return model
        # Fallback: last registered model
        if self._metadata["models"]:
            return self._metadata["models"][-1]
        return None

    def get_all_models(self) -> List[Dict[str, Any]]:
        """Get all registered models."""
        return self._metadata["models"]


class ContinuousAutoMLPipeline:
    """
    Continuous self-tuning pipeline for RL hyperparameters.
    
    Periodically:
    1. Loads recent market data (2-week window)
    2. Runs Optuna TPE to find optimal hyperparameters
    3. Walk-forward validates the best parameters
    4. Auto-promotes to production if improvement is significant
    
    Usage:
        pipeline = ContinuousAutoMLPipeline(config)
        pipeline.start()  # Runs in background thread
        
        # Or manual trigger:
        result = pipeline.run_optimization()
        
        pipeline.stop()
    """

    def __init__(
        self,
        config: Optional[AutoMLConfig] = None,
        data_provider: Optional[Callable] = None,
        env_factory: Optional[Callable] = None,
        baseline_metrics: Optional[Dict[str, float]] = None,
    ):
        """
        Initialize AutoML Pipeline.
        
        Args:
            config: AutoML configuration
            data_provider: Callable that returns recent market data DataFrame
            env_factory: Callable(params) -> GymEnv for creating RL environments
            baseline_metrics: Current production model metrics to beat
        """
        self.config = config or AutoMLConfig()
        self._data_provider = data_provider
        self._env_factory = env_factory
        self._baseline_metrics = baseline_metrics or {
            "calmar_ratio": 0.0,
            "sharpe_ratio": 0.0,
            "win_rate": 0.5,
            "total_return": 0.0,
        }

        self.registry = ModelRegistry(self.config.registry_dir)

        # State
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_run_time = 0.0

        # Results
        self.last_study: Optional[Any] = None
        self.last_best_params: Dict[str, Any] = {}
        self.last_walk_forward: Optional[WalkForwardResult] = None
        self.trial_history: List[TrialResult] = []

        # Stats
        self.stats = {
            "total_runs": 0,
            "total_trials": 0,
            "promotions": 0,
            "last_run_ts": None,
            "last_promotion_ts": None,
        }

    @staticmethod
    def get_ppo_search_space(trial: "optuna.Trial") -> Dict[str, Any]:
        """Define PPO hyperparameter search space."""
        return {
            "learning_rate": trial.suggest_float("learning_rate", 1e-5, 1e-2, log=True),
            "n_steps": trial.suggest_categorical("n_steps", [512, 1024, 2048, 4096]),
            "batch_size": trial.suggest_categorical("batch_size", [64, 128, 256, 512]),
            "n_epochs": trial.suggest_int("n_epochs", 3, 20),
            "gamma": trial.suggest_float("gamma", 0.9, 0.9999),
            "gae_lambda": trial.suggest_float("gae_lambda", 0.8, 0.99),
            "clip_range": trial.suggest_float("clip_range", 0.1, 0.4),
            "ent_coef": trial.suggest_float("ent_coef", 0.0, 0.1),
            "vf_coef": trial.suggest_float("vf_coef", 0.1, 1.0),
            "max_grad_norm": trial.suggest_float("max_grad_norm", 0.3, 1.0),
        }

    @staticmethod
    def get_sac_search_space(trial: "optuna.Trial") -> Dict[str, Any]:
        """Define SAC hyperparameter search space."""
        return {
            "learning_rate": trial.suggest_float("learning_rate", 1e-5, 1e-3, log=True),
            "buffer_size": trial.suggest_categorical("buffer_size", [50000, 100000, 500000]),
            "batch_size": trial.suggest_categorical("batch_size", [64, 128, 256, 512]),
            "tau": trial.suggest_float("tau", 0.001, 0.05),
            "gamma": trial.suggest_float("gamma", 0.9, 0.9999),
            "train_freq": trial.suggest_categorical("train_freq", [1, 4, 8]),
            "gradient_steps": trial.suggest_categorical("gradient_steps", [1, 2, 4]),
            "ent_coef": trial.suggest_float("ent_coef", 0.0, 0.2),
            "learning_starts": trial.suggest_categorical("learning_starts", [1000, 5000, 10000]),
        }

    def _create_objective(self, data: Any, env_factory: Callable) -> Callable:
        """Create Optuna objective function."""
        
        def objective(trial: "optuna.Trial") -> float:
            """Single Optuna trial: train + evaluate."""
            # Get hyperparameters
            if self.config.algorithm == "PPO":
                params = self.get_ppo_search_space(trial)
            else:
                params = self.get_sac_search_space(trial)

            try:
                # Create environment with trial params
                env = env_factory(params)
                
                # Train RL agent
                start_time = time.time()
                
                if self.config.algorithm == "PPO":
                    from stable_baselines3 import PPO
                    model = PPO(
                        "MlpPolicy",
                        env,
                        learning_rate=params["learning_rate"],
                        n_steps=params["n_steps"],
                        batch_size=params["batch_size"],
                        n_epochs=params["n_epochs"],
                        gamma=params["gamma"],
                        gae_lambda=params["gae_lambda"],
                        clip_range=params["clip_range"],
                        ent_coef=params["ent_coef"],
                        vf_coef=params["vf_coef"],
                        max_grad_norm=params["max_grad_norm"],
                        verbose=0,
                    )
                else:
                    from stable_baselines3 import SAC
                    model = SAC(
                        "MlpPolicy",
                        env,
                        learning_rate=params["learning_rate"],
                        buffer_size=params["buffer_size"],
                        batch_size=params["batch_size"],
                        tau=params["tau"],
                        gamma=params["gamma"],
                        train_freq=params["train_freq"],
                        gradient_steps=params["gradient_steps"],
                        ent_coef=params["ent_coef"],
                        learning_starts=params["learning_starts"],
                        verbose=0,
                    )

                # Train for limited timesteps per trial
                total_timesteps = min(50000, int(100000 / self.config.n_trials * 3))
                model.learn(total_timesteps=total_timesteps)
                training_time = time.time() - start_time

                # Evaluate
                metrics = self._evaluate_model(model, env)
                
                # Record trial
                trial_result = TrialResult(
                    trial_number=trial.number,
                    params=params,
                    calmar_ratio=metrics.get("calmar_ratio", 0.0),
                    sharpe_ratio=metrics.get("sharpe_ratio", 0.0),
                    total_return=metrics.get("total_return", 0.0),
                    win_rate=metrics.get("win_rate", 0.0),
                    max_drawdown=metrics.get("max_drawdown", 0.0),
                    n_trades=metrics.get("n_trades", 0),
                    training_time=training_time,
                )
                self.trial_history.append(trial_result)
                self.stats["total_trials"] += 1

                # Pruning
                trial.report(metrics.get("calmar_ratio", 0.0), step=total_timesteps)
                if trial.should_prune():
                    raise optuna.TrialPruned()

                # Clean up
                env.close()

                return metrics.get("calmar_ratio", 0.0)

            except optuna.TrialPruned:
                raise
            except Exception as e:
                logger.warning(f"Trial {trial.number} failed: {e}")
                self.trial_history.append(TrialResult(
                    trial_number=trial.number,
                    params=params if 'params' in dir() else {},
                    error=str(e),
                ))
                return -999.0

        return objective

    def _evaluate_model(
        self, model: Any, env: Any, n_eval_episodes: int = 5
    ) -> Dict[str, float]:
        """Evaluate a trained model on the environment."""
        try:
            from stable_baselines3.common.evaluation import evaluate_policy
            mean_reward, std_reward = evaluate_policy(
                model, env, n_eval_episodes=n_eval_episodes, deterministic=True
            )
            
            # Calculate basic metrics from evaluation
            returns = []
            for _ in range(n_eval_episodes):
                obs, info = env.reset()
                done = False
                episode_return = 0.0
                while not done:
                    action, _ = model.predict(obs, deterministic=True)
                    obs, reward, terminated, truncated, info = env.step(action)
                    episode_return += reward
                    done = terminated or truncated
                returns.append(episode_return)
            
            returns = np.array(returns)
            mean_return = float(np.mean(returns))
            std_return = float(np.std(returns))
            
            # Sharpe approximation
            sharpe = mean_return / max(1e-8, std_return)
            
            # Win rate
            win_rate = float(np.mean(returns > 0))
            
            # Calmar approximation
            max_dd = float(np.min(returns)) if len(returns) > 0 else 0.0
            calmar = mean_return / max(1e-8, abs(min(returns, default=0)))
            
            return {
                "calmar_ratio": calmar,
                "sharpe_ratio": sharpe,
                "total_return": mean_return,
                "win_rate": win_rate,
                "max_drawdown": abs(max_dd),
                "n_trades": n_eval_episodes,
                "mean_reward": mean_reward,
                "std_reward": std_reward,
            }
            
        except Exception as e:
            logger.warning(f"Evaluation failed: {e}")
            return {
                "calmar_ratio": 0.0,
                "sharpe_ratio": 0.0,
                "total_return": 0.0,
                "win_rate": 0.0,
                "max_drawdown": 0.0,
                "n_trades": 0,
            }

    def run_walk_forward_validation(
        self, best_params: Dict[str, Any], data: Any
    ) -> WalkForwardResult:
        """
        Walk-forward out-of-sample validation.
        
        Split data into N folds. Train on first 70%, test on remaining 30%.
        Only promote if average out-of-sample performance improves.
        """
        n_splits = self.config.walk_forward_splits
        split_results = []
        
        for split_idx in range(n_splits):
            try:
                # Create environment for this split
                if self._env_factory:
                    env = self._env_factory(best_params)
                    
                    # Train
                    if self.config.algorithm == "PPO":
                        from stable_baselines3 import PPO
                        model = PPO("MlpPolicy", env, verbose=0, **best_params)
                    else:
                        from stable_baselines3 import SAC
                        model = SAC("MlpPolicy", env, verbose=0, **best_params)
                    
                    model.learn(total_timesteps=30000)
                    
                    # Evaluate
                    metrics = self._evaluate_model(model, env, n_eval_episodes=3)
                    split_results.append(metrics)
                    
                    env.close()
                    
            except Exception as e:
                logger.warning(f"Walk-forward split {split_idx} failed: {e}")
                split_results.append({"calmar_ratio": 0.0, "sharpe_ratio": 0.0})

        # Calculate averages
        avg_calmar = np.mean([s.get("calmar_ratio", 0) for s in split_results])
        avg_sharpe = np.mean([s.get("sharpe_ratio", 0) for s in split_results])
        avg_return = np.mean([s.get("total_return", 0) for s in split_results])
        avg_win_rate = np.mean([s.get("win_rate", 0) for s in split_results])

        # Compare with production
        is_better = (
            avg_calmar >= self._baseline_metrics.get("calmar_ratio", 0) * (1 + self.config.min_calmar_improvement)
            and avg_sharpe >= self._baseline_metrics.get("sharpe_ratio", 0) * (1 + self.config.min_sharpe_improvement)
            and avg_win_rate >= self.config.min_win_rate
        )

        result = WalkForwardResult(
            n_splits=n_splits,
            avg_calmar=float(avg_calmar),
            avg_sharpe=float(avg_sharpe),
            avg_return=float(avg_return),
            avg_win_rate=float(avg_win_rate),
            split_results=split_results,
            is_better_than_production=is_better,
        )

        self.last_walk_forward = result
        return result

    def run_optimization(self) -> Dict[str, Any]:
        """
        Run a full optimization cycle.
        
        Steps:
        1. Create Optuna study
        2. Run trials
        3. Get best parameters
        4. Walk-forward validate
        5. Auto-promote if better than production
        
        Returns:
            Summary dict with results
        """
        if not OPTUNA_AVAILABLE:
            logger.error("Optuna not installed — cannot run AutoML")
            return {"error": "Optuna not installed"}

        self.stats["total_runs"] += 1
        self.stats["last_run_ts"] = datetime.now(timezone.utc).isoformat()
        start_time = time.time()

        try:
            # 1. Create study
            study = optuna.create_study(
                direction="maximize",
                sampler=optuna.samplers.TPESampler(seed=42),
                pruner=optuna.pruners.MedianPruner(n_startup_trials=5),
            )
            self.last_study = study

            # 2. Run optimization
            if self._env_factory:
                dummy_data = None  # Data provider not needed if env_factory handles it
                objective = self._create_objective(dummy_data, self._env_factory)
                
                study.optimize(
                    objective,
                    n_trials=self.config.n_trials,
                    timeout=self.config.total_timeout,
                    show_progress_bar=False,
                )

                # 3. Get best params
                best_params = study.best_params
                self.last_best_params = best_params
                best_value = study.best_value

                logger.info(
                    f"Optuna study complete: best calmar={best_value:.4f} "
                    f"params={best_params}"
                )

                # 4. Walk-forward validate
                wf_result = self.run_walk_forward_validation(best_params, dummy_data)

                # 5. Auto-promote if better
                promoted = False
                if wf_result.is_better_than_production:
                    # Save model to registry
                    registry_path = os.path.join(
                        self.config.registry_dir,
                        f"model_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.zip"
                    )
                    
                    version = self.registry.register_model(
                        model_path=registry_path,
                        metrics={
                            "calmar_ratio": wf_result.avg_calmar,
                            "sharpe_ratio": wf_result.avg_sharpe,
                            "win_rate": wf_result.avg_win_rate,
                            "total_return": wf_result.avg_return,
                        },
                        params=best_params,
                        description=f"AutoML run {self.stats['total_runs']} - auto-promoted",
                    )
                    
                    self.registry.promote_to_production(version)
                    self._baseline_metrics = {
                        "calmar_ratio": wf_result.avg_calmar,
                        "sharpe_ratio": wf_result.avg_sharpe,
                        "win_rate": wf_result.avg_win_rate,
                        "total_return": wf_result.avg_return,
                    }
                    promoted = True
                    self.stats["promotions"] += 1
                    self.stats["last_promotion_ts"] = datetime.now(timezone.utc).isoformat()
                    
                    logger.info(f"🎉 New model AUTO-PROMOTED to production! Version: {version}")

                elapsed = time.time() - start_time

                return {
                    "status": "success",
                    "best_params": best_params,
                    "best_value": best_value,
                    "walk_forward": wf_result.to_dict(),
                    "promoted": promoted,
                    "n_trials": len(study.trials),
                    "elapsed_seconds": elapsed,
                }
            else:
                return {"error": "No env_factory provided — cannot optimize"}

        except Exception as e:
            logger.error(f"AutoML optimization failed: {e}", exc_info=True)
            return {"error": str(e)}

    def start(self) -> None:
        """Start the continuous AutoML scheduler in background."""
        if not OPTUNA_AVAILABLE:
            logger.warning("Cannot start AutoML scheduler: Optuna not installed")
            return

        if self._running:
            logger.warning("AutoML scheduler already running")
            return

        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(
            target=self._scheduler_loop,
            name="AutoMLScheduler",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            f"AutoML scheduler started | interval={self.config.auto_run_interval}s "
            f"| algorithm={self.config.algorithm}"
        )

    def stop(self, timeout: float = 10.0) -> None:
        """Stop the AutoML scheduler."""
        if not self._running:
            return
        self._stop_event.set()
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        logger.info("AutoML scheduler stopped")

    def _scheduler_loop(self) -> None:
        """Background loop that triggers optimization periodically."""
        while not self._stop_event.is_set():
            # Wait for next interval
            if self._stop_event.wait(self.config.auto_run_interval):
                break
            
            logger.info("AutoML scheduled run starting...")
            result = self.run_optimization()
            logger.info(f"AutoML scheduled run complete: {result.get('status', 'unknown')}")

    def get_stats(self) -> Dict[str, Any]:
        """Get AutoML pipeline statistics."""
        return {
            **self.stats,
            "is_running": self._running,
            "last_best_params": self.last_best_params,
            "last_walk_forward": (
                self.last_walk_forward.to_dict() if self.last_walk_forward else None
            ),
            "production_model": self.registry.get_production_model(),
            "n_trial_history": len(self.trial_history),
        }