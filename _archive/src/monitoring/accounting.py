from dataclasses import dataclass
from typing import List


@dataclass
class TradeRecord:
    symbol: str
    buy_price: float
    sell_price: float
    volume: int
    broker_fee_buy_pct: float = 0.0015  # 0.15% buy fee
    broker_fee_sell_pct: float = 0.0025  # 0.25% sell fee (incl. tax)


def calculate_idx_net_profit(trades: List[TradeRecord]) -> dict:
    """
    Kalkulasi Net Profit khusus aturan BEI.

    Returns a dict with gross_profit, broker_fees, idx_final_tax, net_profit,
    and profit_margin_after_tax.
    """
    total_gross_profit = 0.0
    total_fees = 0.0
    total_tax = 0.0
    total_buy_cost = 0.0

    for trade in trades:
        gross_buy_value = float(trade.buy_price) * int(trade.volume)
        gross_sell_value = float(trade.sell_price) * int(trade.volume)

        # Buy fee
        buy_fee = gross_buy_value * float(trade.broker_fee_buy_pct)

        # Sell fee (split broker fee and IDX final tax)
        sell_fee_pure = gross_sell_value * (float(trade.broker_fee_sell_pct) - 0.0010)
        idx_final_tax = gross_sell_value * 0.0010

        total_fees += buy_fee + sell_fee_pure
        total_tax += idx_final_tax

        total_gross_profit += gross_sell_value - gross_buy_value
        total_buy_cost += gross_buy_value

    net_profit = total_gross_profit - total_fees - total_tax

    profit_margin_after_tax = (
        (net_profit / total_buy_cost) if total_buy_cost > 0 else 0.0
    )

    return {
        "gross_profit": float(total_gross_profit),
        "broker_fees": float(total_fees),
        "idx_final_tax": float(total_tax),
        "net_profit": float(net_profit),
        "profit_margin_after_tax": float(profit_margin_after_tax),
    }
