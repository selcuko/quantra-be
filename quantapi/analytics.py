

from quantapi.models import Session, Market


class SessionAnalytics:
    """
    Helper class to calculate session analytics such as capital delta, profit, loss, etc.
    """
    def __init__(self, session:Session) -> None:
        self.session = session
    
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
    def equity_delta_percentage(self):
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
    def capital_delta_percentage(self):
        """
        Calculate the percentage change in capital for the session.

        """
        return (self.capital_delta / self.session.initial_capital) * 100


class MarketAnalytics:
    def __init__(self):
        self.markets = Market.objects.filter(mainnet_enabled=True)

    def capital(self):
        return sum([market.usdt for market in self.markets if market.usdt])
    
    def equity(self):
        return sum([market.equity for market in self.markets if market.equity])
