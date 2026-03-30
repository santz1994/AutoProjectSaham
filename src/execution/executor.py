from datetime import datetime


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
        now = datetime.utcnow().isoformat() + 'Z'
        qty = int(qty)
        if side.lower() == 'buy':
            cost = price * qty
            if cost <= self.cash:
                self.cash -= cost
                self.positions[symbol] = self.positions.get(symbol, 0) + qty
                trade = {'time': now, 'symbol': symbol, 'side': 'buy', 'qty': qty, 'price': price, 'status': 'filled'}
                self.trades.append(trade)
                return trade
            else:
                trade = {'time': now, 'symbol': symbol, 'side': 'buy', 'qty': qty, 'price': price, 'status': 'rejected', 'reason': 'insufficient_cash'}
                self.trades.append(trade)
                return trade

        if side.lower() == 'sell':
            pos = self.positions.get(symbol, 0)
            if qty <= pos:
                self.positions[symbol] = pos - qty
                proceeds = price * qty
                self.cash += proceeds
                trade = {'time': now, 'symbol': symbol, 'side': 'sell', 'qty': qty, 'price': price, 'status': 'filled'}
                self.trades.append(trade)
                return trade
            else:
                trade = {'time': now, 'symbol': symbol, 'side': 'sell', 'qty': qty, 'price': price, 'status': 'rejected', 'reason': 'insufficient_position'}
                self.trades.append(trade)
                return trade

        trade = {'time': now, 'symbol': symbol, 'side': side, 'qty': qty, 'price': price, 'status': 'rejected', 'reason': 'unknown_side'}
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
