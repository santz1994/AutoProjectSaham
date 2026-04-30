"""Gym-style trading environment for RL experiments.

This environment is intentionally small and self-contained so it can be
used for prototyping PPO/other RL algorithms and uses the
`ExecutionManager` + `PaperBroker` for simulated execution.

Fase 3 enhancements:
- Leverage support (max_leverage parameter, margin accounting)
- Realistic slippage & trading fees (maker/taker commission)
- Sharpe Ratio-based reward function
- Death Penalty (liquidation) when equity hits maintenance margin
- Rolling return history for Sharpe computation

Fase 4 enhancements (Asymmetric Reward Shaping):
- Loss penalty multiplier (default 10x) makes losing trades hurt far more
  than winning trades feel good — forces agent to only enter high-probability
  setups and cut losses immediately.
- Quick-cut bonus: small reward for exiting a losing position fast, teaching
  the agent that cutting losses early is better than holding losers.
- Entry patience bonus: tiny reward for holding/no-action when no clear edge,
  discouraging overtrading.
- Sortino-based drawdown penalty: penalizes downside deviation, not total
  volatility, so the agent is rewarded for upside variance.

Action space:
 - 0: hold
 - 1: buy (buy `position_size` units)
 - 2: sell (sell all holdings)
 - 3: cancel pending limits

Observation: numpy vector with [last_price, short_sma, long_sma, volatility,
momentum, dist_to_liquidation, norm_dist_to_liquidation,
position_notional_fraction]
"""
from __future__ import annotations

import math
from collections import deque
from typing import List, Optional

import numpy as np


def _try_import_gym():
    try:
        import gymnasium as gym

        return gym
    except ImportError:
        return None


GYM = _try_import_gym()


class TradingEnv:
    """Lightweight trading environment compatible with gymnasium when available.

    Fase 3: Colosseum — brutal simulation with leverage, slippage, fees,
    Sharpe-based reward, and liquidation (death penalty).

    Fase 4: Asymmetric Reward Shaping — losses are penalized far more
    heavily than wins are rewarded, forcing the agent to only take
    high-probability trades and cut losers fast.
    """

    def __init__(
        self,
        prices: List[float],
        volumes: Optional[List[float]] = None,
        symbol: str = "ENV",
        starting_cash: float = 10000.0,
        position_size: float = 1.0,
        commission_pct: float = 0.001,  # 0.1% taker fee (realistic for Binance)
        slippage_pct: float = 0.0005,  # 0.05% base slippage
        max_leverage: float = 1.0,  # 1.0 = no leverage, 20.0 = 20x
        maintenance_margin_fraction: float = 0.10,  # liquidate at 10% of initial
        sharpe_lookback: int = 50,  # rolling window for Sharpe computation
        risk_free_rate: float = 0.0,  # annualized risk-free rate for Sharpe
        # --- Fase 4: Asymmetric Reward Shaping parameters ---
        loss_penalty_multiplier: float = 10.0,  # losses hurt 10x more than wins
        win_reward_multiplier: float = 1.0,  # baseline win reward scale
        quick_cut_bonus: float = 0.5,  # bonus for exiting a loser fast
        entry_patience_bonus: float = 0.01,  # tiny reward for HOLD (no overtrade)
        drawdown_sortino_threshold: float = 0.10,  # drawdown % before sortino penalty
    ):
        self.prices = list(prices)
        if not self.prices:
            raise ValueError("prices must be non-empty")
        self.symbol = symbol
        self.starting_cash = float(starting_cash)
        self.position_size = float(position_size)
        if (not math.isfinite(self.position_size)) or self.position_size <= 0:
            raise ValueError("position_size must be > 0")

        # --- Fase 3: Realistic cost model ---
        self.commission_pct = float(commission_pct)
        self.slippage_pct = float(slippage_pct)

        # --- Fase 3: Leverage & liquidation ---
        self.max_leverage = max(1.0, float(max_leverage))
        self.maintenance_margin_fraction = float(
            max(0.01, min(maintenance_margin_fraction, 0.50))
        )
        self.liquidation_threshold = (
            self.starting_cash * self.maintenance_margin_fraction
        )

        # --- Fase 3: Sharpe ratio reward ---
        self.sharpe_lookback = max(10, int(sharpe_lookback))
        self.risk_free_rate = float(risk_free_rate)
        self._return_history: deque = deque(maxlen=self.sharpe_lookback)

        # --- Fase 4: Asymmetric Reward Shaping ---
        self.loss_penalty_multiplier = max(1.0, float(loss_penalty_multiplier))
        self.win_reward_multiplier = max(0.1, float(win_reward_multiplier))
        self.quick_cut_bonus = max(0.0, float(quick_cut_bonus))
        self.entry_patience_bonus = max(0.0, float(entry_patience_bonus))
        self.drawdown_sortino_threshold = max(0.01, float(drawdown_sortino_threshold))

        # Track trade entry price for asymmetric P&L calculation
        self._entry_price: Optional[float] = None
        self._steps_in_position: int = 0  # how long we've held current position
        self._total_wins: int = 0
        self._total_losses: int = 0
        self._negative_returns: deque = deque(maxlen=self.sharpe_lookback)

        # optional per-tick volumes for liquidity/slippage modeling
        self.volumes = list(volumes) if volumes is not None else [0] * len(self.prices)

        # internal state
        self.t = 0
        self.cash = self.starting_cash
        self.pos = 0.0
        self._start_balance = self.starting_cash
        self._margin_used = 0.0  # track margin for leveraged positions
        self.active_limit_sell_price: Optional[float] = None
        self._is_liquidated = False  # death penalty flag
        self._peak_equity = self.starting_cash  # for drawdown tracking

        # lazy imports to avoid hard dependencies
        from src.execution.executor import PaperBroker
        from src.execution.manager import ExecutionManager
        from src.ml.feature_store import compute_latest_features

        self.ExecutionManager = ExecutionManager
        self.compute_latest_features = compute_latest_features

        # initialize manager with a PaperBroker seeded with this
        # environment's starting cash
        self.manager = ExecutionManager(broker=PaperBroker(cash=self.starting_cash))
        self.manager.start_day({self.symbol: self.prices[0]})

        # observation/action spaces when gym available
        self.observation_shape = (8,)
        # expose a richer action space: Decision + TakeProfit bracket
        # Decision: 0=Hold, 1=Buy, 2=Sell Market, 3=Cancel Limits
        # TP Bracket: 0=No TP, 1=+2%, 2=+5%, 3=+10%, 4=+15% extension
        if GYM is not None:
            self.action_space = GYM.spaces.MultiDiscrete([4, 5])
            self.observation_space = GYM.spaces.Box(
                low=-1e9, high=1e9, shape=self.observation_shape, dtype=np.float32
            )

    def reset(self, start_index: Optional[int] = None):
        self.t = start_index if start_index is not None else 0
        self.cash = self.starting_cash
        self.pos = 0.0
        self._start_balance = self.starting_cash
        self._margin_used = 0.0
        self._is_liquidated = False
        self._peak_equity = self.starting_cash
        self._return_history.clear()
        # Fase 4: Reset asymmetric tracking
        self._entry_price = None
        self._steps_in_position = 0
        self._negative_returns.clear()
        # recreate manager with broker seeded to this env starting cash so
        # the RL episode has the correct buying power (avoid hardcoded defaults)
        from src.execution.executor import PaperBroker

        self.manager = self.ExecutionManager(
            broker=PaperBroker(cash=self.starting_cash)
        )
        self.manager.start_day({self.symbol: self.prices[self.t]})
        obs = self._get_obs()
        # gymnasium requires reset to return (obs, info)
        if GYM is not None:
            return obs, {}
        return obs

    def _get_obs(self):
        # features from prefix
        prefix = self.prices[: self.t + 1]
        feats = self.compute_latest_features(prefix)
        last = float(prefix[-1])

        # Market-agnostic risk context for 24x5/24x7 products.
        dist_to_liquidation = float(feats.get("dist_to_liquidation", 0.0))
        norm_dist_to_liquidation = float(
            feats.get("norm_dist_to_liquidation", np.tanh(dist_to_liquidation))
        )

        # fetch live broker state so the agent can see its positions/cash
        live_cash = getattr(getattr(self.manager, "broker", None), "cash", self.cash)
        live_pos = 0
        try:
            live_pos = getattr(self.manager.broker, "positions", {}).get(
                self.symbol, float(self.pos)
            )
        except (AttributeError, TypeError, ValueError):
            live_pos = float(self.pos)

        if live_cash is not None:
            total_value = live_cash + (live_pos * last)
        else:
            total_value = self.cash + self.pos * last

        pos_fraction = (live_pos * last) / total_value if total_value > 0 else 0.0

        obs = np.array(
            [
                feats.get("last_price", last),
                feats.get("short_sma", last),
                feats.get("long_sma", last),
                feats.get("volatility", 0.0),
                feats.get("momentum", 0.0),
                dist_to_liquidation,
                norm_dist_to_liquidation,
                pos_fraction,
            ],
            dtype=np.float32,
        )
        return obs

    # ------------------------------------------------------------------
    # Fase 3: Cost & Leverage Helpers
    # ------------------------------------------------------------------

    def _apply_slippage(self, price: float, side: str, volume: float) -> float:
        """Apply realistic slippage to execution price.

        Slippage increases with trade size relative to available volume.
        Uses base slippage_pct + volume-impact component.
        """
        base_slip = self.slippage_pct

        # volume-impact: larger trades relative to volume cause more slippage
        if volume > 0:
            volume_ratio = self.position_size / max(float(volume), 1.0)
            impact = min(0.05, base_slip * (1.0 + volume_ratio * 10.0))
        else:
            impact = base_slip

        if side == "buy":
            return price * (1.0 + impact)
        else:
            return price * (1.0 - impact)

    def _apply_commission(self, notional: float) -> float:
        """Calculate trading fee (commission) on a notional value.

        Fee is always a cost (positive number) deducted from the account.
        Leverage amplifies notional, hence fee is also amplified.
        """
        return abs(notional) * self.commission_pct

    def _get_equity(self, price: Optional[float] = None) -> float:
        """Current equity = cash + position_value - margin_debt."""
        p = price if price is not None else self.prices[min(self.t, len(self.prices) - 1)]
        live_cash = getattr(getattr(self.manager, "broker", None), "cash", self.cash)
        live_pos = 0.0
        try:
            live_pos = float(
                getattr(self.manager.broker, "positions", {}).get(self.symbol, 0.0)
            )
        except (AttributeError, TypeError, ValueError):
            live_pos = float(self.pos)
        return float(live_cash) + live_pos * p - self._margin_used

    def _check_liquidation(self, price: float) -> bool:
        """Check if equity has dropped below maintenance margin.

        If so, force-close all positions (death penalty) and mark episode
        as liquidated.
        """
        equity = self._get_equity(price)
        if equity <= self.liquidation_threshold:
            # Force close all positions at current price
            qty = 0.0
            try:
                qty = float(
                    getattr(self.manager.broker, "positions", {}).get(self.symbol, 0.0)
                )
            except (AttributeError, TypeError, ValueError):
                qty = float(self.pos)

            if qty > 0:
                # Liquidation sale — no favorable slippage, apply max slippage
                liq_price = price * (1.0 - min(0.10, self.slippage_pct * 5))
                self.manager.place_order(self.symbol, "sell", qty, liq_price)

            # Reset margin tracking
            self._margin_used = 0.0
            self._is_liquidated = True
            return True
        return False

    def _compute_sharpe_reward(self, period_return: float) -> float:
        """Compute Sharpe-ratio-based reward from rolling returns.

        Returns a scaled Sharpe value that encourages consistent positive
        returns with low variance. Falls back to simple return when
        insufficient history.
        """
        self._return_history.append(period_return)

        if len(self._return_history) < 5:
            # insufficient history — use scaled return as proxy
            return float(period_return * 100.0)

        returns = np.array(self._return_history, dtype=np.float64)
        mean_ret = float(np.mean(returns))
        std_ret = float(np.std(returns))

        # Risk-free per-period (convert annualized to per-step)
        # Assuming ~252 trading days, ~24*5=120 hourly steps per day for crypto
        rf_per_period = self.risk_free_rate / (252.0 * 24.0)

        if std_ret < 1e-10:
            # zero variance — reward consistent returns
            sharpe = mean_ret * 100.0
        else:
            sharpe = (mean_ret - rf_per_period) / std_ret

        # Scale Sharpe to a reasonable reward range
        # A Sharpe of 2.0 is excellent, scale to ~2.0 reward
        return float(np.clip(sharpe * 2.0, -10.0, 10.0))

    # ------------------------------------------------------------------
    # Fase 4: Asymmetric Reward Shaping Helpers
    # ------------------------------------------------------------------

    def _compute_sortino_penalty(self, period_return: float) -> float:
        """Compute Sortino-ratio-based penalty for downside deviation.

        Unlike Sharpe which penalizes all volatility, Sortino only penalizes
        downside volatility. This means the agent is rewarded for upside
        variance (big wins) while still being punished for losses.
        """
        if period_return < 0:
            self._negative_returns.append(period_return)

        if len(self._negative_returns) < 3:
            return 0.0

        neg_arr = np.array(self._negative_returns, dtype=np.float64)
        downside_std = float(np.sqrt(np.mean(neg_arr**2)))

        if downside_std < 1e-10:
            return 0.0

        # penalty scales with downside deviation magnitude
        # Higher downside_std = more punishment
        penalty = float(np.clip(downside_std * 5.0, 0.0, 5.0))
        return penalty

    def _compute_asymmetric_trade_reward(
        self, pnl_pct: float, steps_held: int
    ) -> float:
        """Compute asymmetric reward for a closed trade.

        Core principle: losses are punished 10x more than wins are rewarded.
        This forces the agent to only enter high-probability setups and to
        cut losses immediately.

        Args:
            pnl_pct: percentage P&L of the trade (e.g., 0.02 = +2%)
            steps_held: how many steps the position was held

        Returns:
            Asymmetric reward value (can be very negative for losses)
        """
        if pnl_pct >= 0:
            # --- WIN: moderate positive reward ---
            # Scale by win_reward_multiplier (default 1.0)
            # Slight bonus for quick wins (good timing)
            time_bonus = max(0.0, 1.0 / max(1, steps_held) * 0.5)
            trade_reward = pnl_pct * 100.0 * self.win_reward_multiplier + time_bonus
            self._total_wins += 1
        else:
            # --- LOSS: HEAVY asymmetric penalty ---
            # loss_penalty_multiplier default = 10.0
            # A -1% loss yields -10.0 reward, while a +1% win yields +1.0
            trade_reward = pnl_pct * 100.0 * self.loss_penalty_multiplier

            # Quick-cut bonus: if the agent exited a loser fast (within a few
            # steps), reduce the penalty slightly — this teaches the agent
            # that cutting losses early is better than holding losers.
            if steps_held <= 3:
                trade_reward += self.quick_cut_bonus  # partially offset penalty

            self._total_losses += 1

        return float(np.clip(trade_reward, -50.0, 20.0))

    # ------------------------------------------------------------------
    # Fase 3: Liquidity Resolution (enhanced from v2)
    # ------------------------------------------------------------------

    def _resolve_liquidity_adjusted_price(
        self,
        base_price: float,
        trade_size: float,
        current_volume: float,
        side: str,
    ) -> tuple[Optional[float], Optional[str]]:
        """Return execution price adjusted by liquidity/slippage.

        When current volume is zero, reject the trade to avoid a simulation
        loophole where agents exploit zero-slippage in illiquid ticks.
        """
        if current_volume is None or float(current_volume) <= 0:
            return None, "no_liquidity_volume_zero"

        max_executable_vol = max(1, int(float(current_volume) * 0.10))
        exec_price = float(base_price)

        if abs(float(trade_size)) > max_executable_vol:
            excess_ratio = (
                abs(float(trade_size)) - max_executable_vol
            ) / max_executable_vol
            slippage_factor = min(0.05, 0.005 * (excess_ratio**1.5))
            if side == "buy":
                exec_price = float(base_price) * (1.0 + slippage_factor)
            else:
                exec_price = float(base_price) * (1.0 - slippage_factor)

        return exec_price, None

    # ------------------------------------------------------------------
    # Main Step Function (Fase 3 + Fase 4 Asymmetric Reward)
    # ------------------------------------------------------------------

    def step(self, action):
        """Execute one environment step.

        Fase 3 enhancements:
        - Slippage applied to every execution price
        - Commission (trading fees) deducted on every trade
        - Leverage amplifies buying power but also fees and risk
        - Sharpe Ratio used as reward basis
        - Death Penalty (liquidation) if equity drops to maintenance margin

        Fase 4 enhancements (Asymmetric Reward Shaping):
        - Winning trades: moderate positive reward (+1x scale)
        - Losing trades: HEAVY negative penalty (-10x scale)
        - Quick-cut bonus: small reward for exiting losers fast
        - Entry patience: tiny reward for HOLD when no clear edge
        - Sortino penalty: punishes downside deviation specifically
        """
        # If already liquidated, return terminal
        if self._is_liquidated:
            obs = self._get_obs()
            if GYM is not None:
                return obs, -1000.0, True, False, {"liquidated": True}
            return obs, -1000.0, True, {"liquidated": True}

        price = float(self.prices[self.t])
        prev_balance = self._get_equity(price)

        info = {}
        reward = 0.0

        # normalize action
        if isinstance(action, (list, tuple)):
            arr = action
        else:
            try:
                if isinstance(action, np.ndarray):
                    arr = action.tolist()
                else:
                    arr = [int(action), 0]
            except (TypeError, ValueError):
                arr = [int(action), 0]

        # decision and take-profit bracket
        if isinstance(arr, (list, tuple)) and len(arr) >= 2:
            decision = int(arr[0])
            tp_bracket = int(arr[1])
        else:
            decision = int(arr[0]) if len(arr) > 0 else int(arr)
            tp_bracket = 0

        # --- Fase 4: Entry patience bonus for HOLD ---
        # Reward the agent for not overtrading when there's no clear signal
        if decision == 0 and self.pos == 0:
            reward += self.entry_patience_bonus
            info["patience_bonus"] = True

        # Track steps in position
        if self.pos > 0:
            self._steps_in_position += 1
        else:
            self._steps_in_position = 0

        # 1) Let manager process any pending limit orders for this tick
        try:
            tick_res = self.manager.process_market_tick({self.symbol: price})
            if tick_res.get("executed"):
                for e in tick_res["executed"]:
                    if e.get("order", {}).get("symbol") == self.symbol:
                        info["limit_executed"] = True
                        # Fase 4: If TP triggered, compute asymmetric reward
                        if self._entry_price is not None and self._entry_price > 0:
                            pnl_pct = (price - self._entry_price) / self._entry_price
                            asym_reward = self._compute_asymmetric_trade_reward(
                                pnl_pct, self._steps_in_position
                            )
                            reward += asym_reward
                            info["tp_asymmetric_reward"] = float(asym_reward)
                            info["tp_pnl_pct"] = float(pnl_pct * 100.0)
                            self._entry_price = None
                            self._steps_in_position = 0
                        else:
                            reward += 2.0
                        break
        except (AttributeError, KeyError, TypeError, ValueError):
            # non-fatal: continue processing action
            pass

        # 2) Process incoming decision
        if decision == 1:
            # BUY market (with leverage)
            current_volume = self.volumes[self.t] if self.t < len(self.volumes) else 0
            trade_size = float(self.position_size)

            # Fase 3: Apply slippage to execution price
            current_volume_f = float(current_volume) if current_volume else 0
            exec_price, liquidity_error = self._resolve_liquidity_adjusted_price(
                base_price=price,
                trade_size=trade_size,
                current_volume=current_volume_f,
                side="buy",
            )
            if liquidity_error:
                reward -= 2.0
                info["rejected"] = liquidity_error
                info["liquidity_penalty"] = True
                exec_price = None

            if exec_price is None:
                trade = {"status": "rejected", "reason": liquidity_error}
            else:
                # Fase 3: Apply additional slippage model
                exec_price = self._apply_slippage(exec_price, "buy", current_volume_f)

                # Fase 3: Leverage — buying power is amplified
                leveraged_size = trade_size * self.max_leverage
                buy_notional = exec_price * leveraged_size

                # Fase 3: Commission on the leveraged notional
                fee = self._apply_commission(buy_notional)
                margin_debt = buy_notional * (1.0 - 1.0 / self.max_leverage) if self.max_leverage > 1.0 else 0.0

                # Check if we have enough cash for the fee + initial margin
                available_cash = getattr(
                    getattr(self.manager, "broker", None), "cash", self.cash
                )
                if available_cash < fee + (buy_notional / self.max_leverage if self.max_leverage > 1.0 else buy_notional):
                    reward -= 1.0
                    info["rejected"] = "insufficient_margin"
                    trade = {"status": "rejected", "reason": "insufficient_margin"}
                else:
                    trade = self.manager.place_order(
                        self.symbol,
                        "buy",
                        trade_size,
                        exec_price,
                    )

                    if trade.get("status") != "rejected":
                        # Deduct commission from cash
                        try:
                            self.manager.broker.cash -= fee
                        except (AttributeError, TypeError):
                            pass
                        self._margin_used += margin_debt
                        info["fee_paid"] = float(fee)
                        info["leverage_used"] = float(self.max_leverage)
                        info["margin_debt"] = float(margin_debt)

                        # Fase 4: Track entry price for asymmetric P&L
                        self._entry_price = float(exec_price)
                        self._steps_in_position = 0

            if trade.get("status") == "rejected":
                reward -= 1.0
                info["rejected"] = trade.get("reason")
            else:
                # set take-profit target based on bracket
                limit_price = None
                if tp_bracket == 1:
                    limit_price = price * 1.02
                elif tp_bracket == 2:
                    limit_price = price * 1.05
                elif tp_bracket == 3:
                    limit_price = price * 1.10
                elif tp_bracket == 4:
                    limit_price = price * 1.15

                if limit_price is not None:
                    # register pending limit with manager
                    res = self.manager.place_limit_order(
                        self.symbol,
                        "sell",
                        self.position_size,
                        limit_price,
                    )
                    if res.get("status") == "pending":
                        info["limit_order_id"] = res.get("order_id")
                        info["limit_set"] = float(limit_price)
                        self.active_limit_sell_price = float(limit_price)
                    else:
                        info["limit_rejected"] = res.get("reason")

        elif decision == 2:
            # SELL market (manual override)
            qty = self.manager.broker.positions.get(self.symbol, 0)
            if float(qty) > 0:
                current_volume = (
                    self.volumes[self.t] if self.t < len(self.volumes) else 0
                )
                trade_size = float(qty)
                current_volume_f = float(current_volume) if current_volume else 0

                exec_price, liquidity_error = self._resolve_liquidity_adjusted_price(
                    base_price=price,
                    trade_size=trade_size,
                    current_volume=current_volume_f,
                    side="sell",
                )
                if liquidity_error:
                    reward -= 2.0
                    info["rejected"] = liquidity_error
                    info["liquidity_penalty"] = True
                    trade = {"status": "rejected", "reason": liquidity_error}
                else:
                    # Fase 3: Apply slippage on sell
                    exec_price = self._apply_slippage(exec_price, "sell", current_volume_f)

                    sell_notional = exec_price * trade_size
                    # Fase 3: Commission on sell (leverage-amplified)
                    leveraged_sell = sell_notional * self.max_leverage
                    fee = self._apply_commission(leveraged_sell)

                    trade = self.manager.place_order(
                        self.symbol,
                        "sell",
                        qty,
                        exec_price,
                    )

                    if trade.get("status") != "rejected":
                        # Deduct commission
                        try:
                            self.manager.broker.cash -= fee
                        except (AttributeError, TypeError):
                            pass
                        # Release margin
                        self._margin_used = max(
                            0.0,
                            self._margin_used - sell_notional * (1.0 - 1.0 / self.max_leverage)
                            if self.max_leverage > 1.0
                            else 0.0,
                        )
                        info["fee_paid"] = float(fee)

                        # Fase 4: Compute asymmetric trade reward on sell
                        if self._entry_price is not None and self._entry_price > 0:
                            pnl_pct = (float(exec_price) - self._entry_price) / self._entry_price
                            asym_reward = self._compute_asymmetric_trade_reward(
                                pnl_pct, self._steps_in_position
                            )
                            reward += asym_reward
                            info["asymmetric_trade_reward"] = float(asym_reward)
                            info["trade_pnl_pct"] = float(pnl_pct * 100.0)
                            info["trade_result"] = "win" if pnl_pct >= 0 else "loss"
                            self._entry_price = None
                            self._steps_in_position = 0

                if trade.get("status") == "rejected":
                    reward -= 1.0
                    info["rejected"] = trade.get("reason")
                else:
                    # clear any pending TP / limit orders for this symbol
                    cancelled = self.manager.cancel_all_pending_for_symbol(self.symbol)
                    info["cancelled_pending"] = int(cancelled)
                    self.active_limit_sell_price = None

        elif decision == 3:
            # cancel pending limits for this symbol
            cancelled = self.manager.cancel_all_pending_for_symbol(self.symbol)
            info["cancelled_pending"] = int(cancelled)
            self.active_limit_sell_price = None

        # Fase 3: Check for liquidation (death penalty)
        current_price = self.prices[self.t]
        if self._check_liquidation(current_price):
            reward = -1000.0  # DEATH PENALTY
            info["liquidated"] = True
            info["death_penalty"] = True
            done = True
            obs = self._get_obs()
            if GYM is not None:
                return obs, float(reward), bool(done), False, info
            return obs, float(reward), bool(done), info

        # advance time
        done = False
        self.t += 1
        if self.t >= len(self.prices):
            done = True

        # Fase 3: Compute equity-based return
        new_price = self.prices[self.t - 1] if self.t - 1 < len(self.prices) else price
        new_balance = self._get_equity(new_price)

        period_return = (float(new_balance) - float(prev_balance)) / max(
            float(prev_balance), 1e-6,
        )

        # Fase 3: Update peak equity for drawdown tracking
        if new_balance > self._peak_equity:
            self._peak_equity = new_balance

        # Fase 3: Sharpe-ratio-based reward
        sharpe_reward = self._compute_sharpe_reward(period_return)
        reward += sharpe_reward

        # Fase 3: Drawdown penalty (subtle)
        if self._peak_equity > 0:
            drawdown = (self._peak_equity - new_balance) / self._peak_equity
            if drawdown > 0.20:  # >20% drawdown
                reward -= float(drawdown * 5.0)

        # Fase 4: Sortino-based downside penalty
        sortino_penalty = self._compute_sortino_penalty(period_return)
        if sortino_penalty > 0:
            reward -= sortino_penalty
            info["sortino_penalty"] = float(sortino_penalty)

        info["period_return_pct"] = float(period_return * 100.0)
        info["sharpe_reward"] = float(sharpe_reward)
        info["equity"] = float(new_balance)
        info["drawdown_pct"] = float(
            (self._peak_equity - new_balance) / self._peak_equity * 100.0
            if self._peak_equity > 0
            else 0.0
        )
        info["leverage"] = float(self.max_leverage)
        info["win_rate"] = float(
            self._total_wins / max(1, self._total_wins + self._total_losses) * 100.0
        )
        info["total_wins"] = int(self._total_wins)
        info["total_losses"] = int(self._total_losses)
        info["steps_in_position"] = int(self._steps_in_position)

        # Always return a valid observation (SB3 requires an observation
        # even at terminal)
        obs = self._get_obs()

        # include info about active TP for debugging
        if getattr(self, "active_limit_sell_price", None) is not None:
            info["active_limit"] = float(self.active_limit_sell_price)

        # gymnasium expects: obs, reward, terminated, truncated, info
        if GYM is not None:
            return obs, float(reward), bool(done), False, info
        return obs, float(reward), bool(done), info

    def render(self):
        bal = self._get_equity()
        price_str = self.prices[self.t - 1] if self.t > 0 else self.prices[0]
        pos = self.manager.broker.positions.get(self.symbol, 0)
        cash = self.manager.broker.cash
        lev = self.max_leverage
        status = "LIQUIDATED" if self._is_liquidated else "ACTIVE"
        wr = self._total_wins / max(1, self._total_wins + self._total_losses) * 100.0
        print(
            f"t={self.t} price={price_str:.2f} cash={cash:.2f} "
            f"pos={pos} equity={bal:.2f} leverage={lev}x "
            f"winrate={wr:.1f}% status={status}"
        )