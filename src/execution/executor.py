from datetime import datetime, timezone


class BrokerInterface:
    """Simple broker interface spec."""

    def place_order(self, symbol, side, qty, price):
        raise NotImplementedError()

    def cancel_order(self, order_id):
        raise NotImplementedError()

    def get_balance(self, price_map=None):
        raise NotImplementedError()


class PaperBroker(BrokerInterface):
    """A minimal paper trading broker simulator.

    - Maintains cash and integer position sizes per symbol
    - Executes market orders immediately at provided price
    - Records trades in-memory
    """

    def __init__(self, cash: float = 10000.0):
        self.cash = float(cash)
        self.positions = {}
        self.trades = []

    def place_order(self, symbol: str, side: str, qty: int, price: float):
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        qty = int(qty)
        # realistic broker fees (approx): buy fee ~0.15%, sell fee ~0.25% (incl. taxes)
        buy_fee_pct = 0.0015
        sell_fee_pct = 0.0025

        if side.lower() == "buy":
            cost = price * qty
            fee = cost * buy_fee_pct
            total_cost = cost + fee
            if total_cost <= self.cash:
                self.cash -= total_cost
                self.positions[symbol] = self.positions.get(symbol, 0) + qty
                trade = {
                    "time": now,
                    "symbol": symbol,
                    "side": "buy",
                    "qty": qty,
                    "price": price,
                    "status": "filled",
                    "fee": float(fee),
                }
                self.trades.append(trade)
                return trade
            else:
                trade = {
                    "time": now,
                    "symbol": symbol,
                    "side": "buy",
                    "qty": qty,
                    "price": price,
                    "status": "rejected",
                    "reason": "insufficient_cash",
                    "required": float(total_cost),
                }
                self.trades.append(trade)
                return trade

        if side.lower() == "sell":
            pos = self.positions.get(symbol, 0)
            if qty <= pos:
                self.positions[symbol] = pos - qty
                proceeds = price * qty
                fee = proceeds * sell_fee_pct
                net = proceeds - fee
                self.cash += net
                trade = {
                    "time": now,
                    "symbol": symbol,
                    "side": "sell",
                    "qty": qty,
                    "price": price,
                    "status": "filled",
                    "fee": float(fee),
                    "net": float(net),
                }
                self.trades.append(trade)
                return trade
            else:
                trade = {
                    "time": now,
                    "symbol": symbol,
                    "side": "sell",
                    "qty": qty,
                    "price": price,
                    "status": "rejected",
                    "reason": "insufficient_position",
                }
                self.trades.append(trade)
                return trade

        trade = {
            "time": now,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "status": "rejected",
            "reason": "unknown_side",
        }
        self.trades.append(trade)
        return trade

    def cancel_order(self, order_id):
        # PaperBroker executes immediately; no order queue implemented.
        return False

    def get_balance(self, price_map: dict = None):
        """Return cash + market value computed with provided price_map.

        price_map: dict symbol -> price
        """
        total = float(self.cash)
        if price_map:
            for sym, qty in self.positions.items():
                last_price = price_map.get(sym)
                if last_price is not None:
                    total += qty * last_price
        return total
