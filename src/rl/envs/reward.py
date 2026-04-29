"""
Reward function module for TradingEnv.

Extracted from trading_env.py as part of the modularization effort.
Contains all reward/penalty computation logic:
- Sharpe Ratio reward
- Sortino Ratio reward
- Death Penalty (liquidation)
- Asymmetric Penalty (losses weighted heavier than gains)
- PnL Penalty
- Regime Penalty
- Activity Bonus
"""
from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Sharpe / Sortino helpers
# ---------------------------------------------------------------------------

def _sharpe_ratio(returns: list[float], risk_free: float = 0.0) -> float:
    """Annualized Sharpe ratio from a list of period returns."""
    if len(returns) < 2:
        return 0.0
    arr = np.array(returns, dtype=np.float64) - risk_free
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1))
    if std < 1e-12:
        return 0.0
    return mean / std * np.sqrt(252)


def _sortino_ratio(returns: list[float], risk_free: float = 0.0) -> float:
    """Annualized Sortino ratio — penalizes only downside volatility."""
    if len(returns) < 2:
        return 0.0
    arr = np.array(returns, dtype=np.float64) - risk_free
    mean = float(np.mean(arr))
    downside = arr[arr < 0]
    if len(downside) < 1:
        return 0.0
    down_std = float(np.std(downside, ddof=1))
    if down_std < 1e-12:
        return 0.0
    return mean / down_std * np.sqrt(252)


# ---------------------------------------------------------------------------
# Reward components
# ---------------------------------------------------------------------------

def compute_sortino_reward(recent_returns: list[float]) -> float:
    """Sortino-based reward component (consistency bonus)."""
    if len(recent_returns) < 5:
        return 0.0
    sortino = _sortino_ratio(recent_returns)
    return float(np.clip(sortino * 0.01, -1.0, 1.0))


def death_penalty(current_step: int, max_steps: int, portfolio_value: float,
                  initial_capital: float, maintenance_margin_ratio: float = 0.1) -> float | None:
    """
    Death penalty when portfolio falls below maintenance margin.
    Returns penalty value or None if no penalty triggered.
    """
    threshold = initial_capital * maintenance_margin_ratio
    if portfolio_value <= threshold:
        progress = current_step / max(1, max_steps)
        return -1000.0 * (1.0 - 0.5 * progress)
    return None


def asymmetric_penalty(pnl: float, asym_loss_weight: float = 2.0,
                       asym_small_threshold: float = 0.001) -> float:
    """
    Asymmetric penalty: losses weighted heavier than gains.
    Small losses get extra penalty to discourage frequent losing trades.
    """
    if pnl < 0:
        abs_pnl = abs(pnl)
        weight = asym_loss_weight * 1.5 if abs_pnl < asym_small_threshold else asym_loss_weight
        return pnl * weight
    return pnl


def pnl_penalty(recent_returns: list[float], pnl_penalty_threshold: int = 5) -> float:
    """
    Additional penalty for consecutive losing trades.
    Returns negative reward if too many consecutive losses detected.
    """
    if len(recent_returns) < pnl_penalty_threshold:
        return 0.0
    recent = recent_returns[-pnl_penalty_threshold:]
    if all(r < 0 for r in recent):
        return -0.5
    return 0.0


def regime_penalty(regime_label: int, current_regime_risk: float = 0.0) -> float:
    """
    Regime-based penalty: extra penalty in high-risk regimes.
    regime_label: 0=ranging, 1=trending, 2=volatile, 3=crash
    """
    if regime_label == 3:  # crash regime
        return -0.3
    if regime_label == 2 and current_regime_risk > 0.7:  # volatile + high risk
        return -0.15
    return 0.0


def activity_bonus(trades_executed: int, current_step: int,
                   activity_bonus_threshold: int = 50) -> float:
    """
    Small activity bonus to encourage exploration early in training.
    Decays as episode progresses.
    """
    if current_step < activity_bonus_threshold and trades_executed == 0:
        return 0.001
    return 0.0


# ---------------------------------------------------------------------------
# Main reward computation
# ---------------------------------------------------------------------------

def compute_reward(
    pnl: float,
    portfolio_value: float,
    initial_capital: float,
    recent_returns: list[float],
    current_step: int,
    max_steps: int,
    regime_label: int = 0,
    current_regime_risk: float = 0.0,
    trades_executed: int = 0,
    maintenance_margin_ratio: float = 0.1,
    asym_loss_weight: float = 2.0,
    asym_small_threshold: float = 0.001,
    pnl_penalty_threshold: int = 5,
    activity_bonus_threshold: int = 50,
) -> tuple[float, bool]:
    """
    Compute the total reward for the current step.

    Returns:
        (reward, terminated): reward value and whether episode should end.
    """
    # Check death penalty first
    dp = death_penalty(current_step, max_steps, portfolio_value,
                       initial_capital, maintenance_margin_ratio)
    if dp is not None:
        return dp, True

    # Base PnL with asymmetric weighting
    reward = asymmetric_penalty(pnl, asym_loss_weight, asym_small_threshold)

    # Sortino consistency bonus
    sortino_bonus = compute_sortino_reward(recent_returns)
    reward += sortino_bonus

    # Consecutive loss penalty
    reward += pnl_penalty(recent_returns, pnl_penalty_threshold)

    # Regime penalty
    reward += regime_penalty(regime_label, current_regime_risk)

    # Activity bonus (exploration encouragement)
    reward += activity_bonus(trades_executed, current_step, activity_bonus_threshold)

    return reward, False