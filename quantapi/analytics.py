from quantapi.models import Order, Session, Market, Signal


class SessionAnalytics:
    """
    Helper class to calculate session analytics such as capital delta, profit, loss, etc.
    """
    def __init__(self, session:Session) -> None:
        self.session = session

    @property
    def orders(self):
        return Order.objects.filter(signal__session=self.session, status=Order.Status.FILLED).count()
    
    @property
    def signals(self):
        return Signal.objects.filter(session=self.session).count()

    @property
    def open_position(self):
        order = Order.objects.filter(signal__session=self.session, status=Order.Status.FILLED).last()
        if order and order.signal.side == Signal.Side.BUY:
            return order
        return None

    @property
    def open_position_delta(self):
        if not self.open_position:
            return None
        in_price = self.open_position.price
        if not self.session.last_price:
            return None
        return self.session.last_price - in_price

    @property
    def open_position_delta_pct(self):
        if not self.open_position:
            return None
        in_price = self.open_position.price
        if not self.session.last_price:
            return None
        return (self.session.last_price - in_price) / in_price * 100

    @property
    def initial_value(self):
        """
        Calculate the initial value for the session.

        """
        if self.session.initial_price:
            return self.session.initial_capital + self.session.initial_price * self.session.initial_assets
        else:
            return self.session.initial_capital

    @property
    def assets_value(self):
        """
        Calculate the value of the assets for the session.

        """
        return self.session.assets * self.session.last_price if self.session.assets and self.session.last_price else 0

    @property
    def equity(self):
        """
        Calculate the equity (total current value) for the session.

        """
        return self.session.capital + self.assets_value
    
    @property
    def equity_delta(self):
        """
        Calculate the change in equity for the session.

        """
        return self.equity - self.initial_value

    @property
    def equity_delta_pct(self):
        """
        Calculate the percentage change in equity for the session.

        """
        return (self.equity_delta / self.initial_value) * 100

    @property
    def capital_delta(self):
        """
        Calculate the change in capital for the session.

        """
        return self.session.capital - self.session.initial_capital
    
    @property
    def capital_delta_pct(self):
        """
        Calculate the percentage change in capital for the session.

        """
        return (self.capital_delta / self.session.initial_capital) * 100


class TotalSessionAnalytics:
    def __init__(self, sessions=None) -> None:
        self.sessions = sessions or Session.objects.filter(status=Session.Status.ONGOING)
        self.sessions = self.sessions.exclude(symbol__market__mainnet_enabled=False)
    
    def capital(self):
        return sum([session.capital for session in self.sessions])
    
    def equity(self):
        return sum([session.assets * session.last_price for session in self.sessions if session.assets and session.last_price])
    
    def open_positions(self):
        # return the number of open positions for the sessions (i.e. last order was a BUY with status FILLED)
        count = 0
        for session in self.sessions:
            order = Order.objects.filter(signal__session=session, status=Order.Status.FILLED).last()
            if order and order.signal.side == Signal.Side.BUY:
                count += 1
        return count
    
    def count(self):
        return self.sessions.count()



class MarketAnalytics:
    def __init__(self):
        self.markets = Market.objects.filter(mainnet_enabled=True)

    def capital(self):
        return sum([market.usdt for market in self.markets if market.usdt])
    
    def equity(self):
        return sum([market.equity for market in self.markets if market.equity])
