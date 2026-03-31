"""Lightweight Optuna wrapper with a fallback random-search optimizer.

The API accepts an objective callable and a simple parameter space spec and
returns the best-found parameters and score. If `optuna` is installed, it
will be used; otherwise a deterministic random-search fallback runs.
"""
from __future__ import annotations

import logging
import random
from typing import Any, Callable, Dict, Tuple

try:
    import optuna  # type: ignore
    OPTUNA_AVAILABLE = True
except Exception:
    OPTUNA_AVAILABLE = False


def optimize(
    objective_fn: Callable[..., float],
    param_space: Dict[str, Tuple[Any, Any, str]],
    n_trials: int = 20,
    random_state: int = 42,
) -> Tuple[Dict[str, Any], float]:
    """Optimize `objective_fn` over `param_space`.

    param_space: dict mapping param -> (low, high, type) where type is 'int' or 'float'.
    objective_fn: callable receiving named parameters and returning a float score (larger is better).

    Returns (best_params, best_score).
    """
    logger = logging.getLogger('autosaham.ml.optuna')

    if OPTUNA_AVAILABLE:
        study = optuna.create_study(direction='maximize')

        def _obj(trial):
            params = {}
            for name, (low, high, ptype) in param_space.items():
                if ptype == 'int':
                    params[name] = trial.suggest_int(name, int(low), int(high))
                else:
                    params[name] = trial.suggest_float(name, float(low), float(high))
            return float(objective_fn(**params))

        study.optimize(_obj, n_trials=n_trials)
        return dict(study.best_params), float(study.best_value)

    # fallback: deterministic pseudo-random search that guarantees coverage
    random.seed(int(random_state))
    best_score = float('-inf')
    best_params: Dict[str, Any] = {}

    # Pre-generate integer sampling sequences to try to cover ranges when possible
    int_param_samples: Dict[str, list] = {}
    for name, (low, high, ptype) in param_space.items():
        if ptype == 'int':
            low_i = int(low)
            high_i = int(high)
            pool = list(range(low_i, high_i + 1))
            if n_trials >= len(pool):
                random.shuffle(pool)
                # if n_trials > pool size, extend with random choices
                extras = []
                if n_trials > len(pool):
                    extras = random.choices(pool, k=(n_trials - len(pool)))
                int_param_samples[name] = pool + extras
            else:
                # sample with replacement
                int_param_samples[name] = [random.randint(low_i, high_i) for _ in range(n_trials)]

    for t in range(n_trials):
        params = {}
        for name, (low, high, ptype) in param_space.items():
            if ptype == 'int':
                params[name] = int_param_samples[name][t]
            else:
                params[name] = random.uniform(float(low), float(high))

        try:
            score = float(objective_fn(**params))
        except Exception as e:
            logger.exception('objective failed on trial %d: %s', t, e)
            score = float('-inf')

        if score > best_score:
            best_score = score
            best_params = dict(params)

    return best_params, best_score
