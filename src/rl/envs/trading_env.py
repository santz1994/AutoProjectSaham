"""Gym-style trading environment for RL experiments.

This environment is intentionally small and self-contained so it can be
used for prototyping PPO/other RL algorithms. It enforces IDX guardrails
and uses the `ExecutionManager` + `PaperBroker` for simulated execution.

Action space:
 - 0: hold
 - 1: buy (buy `position_size` units)
 - 2: sell (sell all holdings)
 - 3: cancel pending limits

Observation: numpy vector with [last_price, short_sma, long_sma, volatility,
momentum, distance_to_ara, distance_to_arb, position_notional_fraction]
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np


def _try_import_gym():
    try:
        import gymnasium as gym

        return gym
    except Exception:
        return None


GYM = _try_import_gym()


class TradingEnv:
    """Lightweight trading environment compatible with gymnasium when available."""

    def __init__(
        self,
        prices: List[float],
        volumes: Optional[List[float]] = None,
        symbol: str = "ENV",
        starting_cash: float = 10000.0,
        position_size: int = 1,
        commission_pct: float = 0.0005,
        slippage_pct: float = 0.0005,
    ):
        self.prices = list(prices)
        if not self.prices:
            raise ValueError("prices must be non-empty")
        self.symbol = symbol
        self.starting_cash = float(starting_cash)
        self.position_size = int(position_size)
        self.commission_pct = float(commission_pct)
        self.slippage_pct = float(slippage_pct)

        # optional per-tick volumes for liquidity/slippage modeling
        self.volumes = list(volumes) if volumes is not None else [0] * len(self.prices)

        # internal state
        self.t = 0
        self.cash = self.starting_cash
        self.pos = 0
        self._start_balance = self.starting_cash

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
        # TP Bracket: 0=No TP, 1=+2%, 2=+5%, 3=+10%, 4=+ARA Limit
        if GYM is not None:
            self.action_space = GYM.spaces.MultiDiscrete([4, 5])
            self.observation_space = GYM.spaces.Box(
                low=-1e9, high=1e9, shape=self.observation_shape, dtype=np.float32
            )

        # TradingEnv no longer tracks pending limit orders itself; use ExecutionManager

    def reset(self, start_index: Optional[int] = None):
        self.t = start_index if start_index is not None else 0
        self.cash = self.starting_cash
        self.pos = 0
        self._start_balance = self.starting_cash
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

        # idx guardrails: use previous close when possible (IDX rules)
        prev_close = float(prefix[-2]) if len(prefix) > 1 else last
        from src.execution.idx_rules import calculate_idx_limits

        limits = calculate_idx_limits(prev_close)
        ara = limits["ara"]
        arb = limits["arb"]

        # distance to bounds (normalized)
        dist_ara = (ara - last) / last if last > 0 else 0.0
        dist_arb = (last - arb) / last if last > 0 else 0.0

        # fetch live broker state so the agent can see its positions/cash
        live_cash = getattr(getattr(self.manager, "broker", None), "cash", self.cash)
        live_pos = 0
        try:
            live_pos = getattr(self.manager.broker, "positions", {}).get(
                self.symbol, int(self.pos)
            )
        except Exception:
            live_pos = int(self.pos)

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
                dist_ara,
                dist_arb,
                pos_fraction,
            ],
            dtype=np.float32,
        )
        return obs

    def step(self, action):
        # action can be scalar (legacy) or array-like [decision, tp_bracket]
        price = float(self.prices[self.t])
        prev_balance = self.manager.get_balance({self.symbol: price})

        info = {}
        reward = 0.0

        # normalize action
        if isinstance(action, (list, tuple)):
            arr = action
        else:
            try:
                import numpy as _np

                if isinstance(action, _np.ndarray):
                    arr = action.tolist()
                else:
                    arr = [int(action), 0]
            except Exception:
                arr = [int(action), 0]

        # decision and take-profit bracket
        if isinstance(arr, (list, tuple)) and len(arr) >= 2:
            decision = int(arr[0])
            tp_bracket = int(arr[1])
        else:
            decision = int(arr[0]) if len(arr) > 0 else int(arr)
            tp_bracket = 0

        # compute previous close for IDX rules and order placement
        prev_close = float(self.prices[self.t - 1]) if self.t > 0 else price

        # 1) Let manager process any pending limit orders for this tick
        try:
            tick_res = self.manager.process_market_tick({self.symbol: price})
            if tick_res.get("executed"):
                for e in tick_res["executed"]:
                    if e.get("order", {}).get("symbol") == self.symbol:
                        info["limit_executed"] = True
                        reward += 2.0
                        break
        except Exception:
            # non-fatal: continue processing action
            pass

        # 2) Process incoming decision
        if decision == 1:
            # BUY market
            # liquidity-aware slippage model (10% of daily volume is liquid)
            current_volume = self.volumes[self.t] if self.t < len(self.volumes) else 0
            trade_size = int(self.position_size)
            max_executable_vol = (
                max(1, int(current_volume * 0.10)) if current_volume else None
            )

            exec_price = price
            if max_executable_vol and abs(trade_size) > max_executable_vol:
                excess_ratio = (
                    abs(trade_size) - max_executable_vol
                ) / max_executable_vol
                slippage_factor = min(0.05, 0.005 * (excess_ratio**1.5))
                exec_price = price * (1.0 + slippage_factor)

            trade = self.manager.place_order(
                self.symbol,
                "buy",
                self.position_size,
                exec_price,
                previous_close=prev_close,
            )
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
                    from src.execution.idx_rules import calculate_idx_limits

                    limits = calculate_idx_limits(prev_close)
                    limit_price = limits["ara"]

                if limit_price is not None:
                    # register pending limit with manager
                    res = self.manager.place_limit_order(
                        self.symbol,
                        "sell",
                        self.position_size,
                        limit_price,
                        previous_close=prev_close,
                    )
                    if res.get("status") == "pending":
                        info["limit_order_id"] = res.get("order_id")
                        info["limit_set"] = float(limit_price)
                    else:
                        info["limit_rejected"] = res.get("reason")

        elif decision == 2:
            # SELL market (manual override)
            qty = self.manager.broker.positions.get(self.symbol, 0)
            if qty > 0:
                current_volume = (
                    self.volumes[self.t] if self.t < len(self.volumes) else 0
                )
                trade_size = int(qty)
                max_executable_vol = (
                    max(1, int(current_volume * 0.10)) if current_volume else None
                )

                exec_price = price
                if max_executable_vol and abs(trade_size) > max_executable_vol:
                    excess_ratio = (
                        abs(trade_size) - max_executable_vol
                    ) / max_executable_vol
                    slippage_factor = min(0.05, 0.005 * (excess_ratio**1.5))
                    exec_price = price * (1.0 - slippage_factor)

                trade = self.manager.place_order(
                    self.symbol, "sell", qty, exec_price, previous_close=prev_close
                )
                if trade.get("status") == "rejected":
                    reward -= 1.0
                    info["rejected"] = trade.get("reason")
                else:
                    # clear any pending TP / limit orders for this symbol
                    cancelled = self.manager.cancel_all_pending_for_symbol(self.symbol)
                    info["cancelled_pending"] = int(cancelled)

        elif decision == 3:
            # cancel pending limits for this symbol
            cancelled = self.manager.cancel_all_pending_for_symbol(self.symbol)
            info["cancelled_pending"] = int(cancelled)

        # advance time
        done = False
        self.t += 1
        if self.t >= len(self.prices):
            done = True

        new_balance = self.manager.get_balance(
            {
                self.symbol: self.prices[self.t - 1]
                if self.t - 1 < len(self.prices)
                else price
            }
        )
        reward += float(new_balance - prev_balance)

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
        bal = self.manager.get_balance(
            {self.symbol: self.prices[self.t - 1] if self.t > 0 else self.prices[0]}
        )
        price_str = self.prices[self.t - 1] if self.t > 0 else self.prices[0]
        pos = self.manager.broker.positions.get(self.symbol, 0)
        cash = self.manager.broker.cash
        print(f"t={self.t} price={price_str} cash={cash}")
        print(f"pos={pos} balance={bal}")
