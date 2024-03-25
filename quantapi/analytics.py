from audioop import avg
from datetime import timedelta
from quantapi.models import Order, Session, Market, Signal


class SessionAnalytics:
    """
    Helper class to calculate session analytics such as capital delta, profit, loss, etc.
    """
    def __init__(self, session:Session) -> None:
        self.session = session
        # prefetch orders and signals
        self.orders = session.orders.filter(status=Order.Status.FILLED)
        self.signals = session.signals.all()

    @property
    def orders_count(self):
        return self.orders.count()
    
    @property
    def signals_count(self):
        return self.signals.count()

    @property
    def open_position(self):
        order = self.orders.last()
        if order and order.side == Order.Side.BUY:
            return order
        return None

    @property
    def real_price(self):
        buyable_amount = (self.initial_value + self.total_pnl) / self.session.last_price if self.session.last_price and self.total_pnl else None
        return self.initial_value / buyable_amount if buyable_amount else None

    @property
    def open_position_delta(self):
        if not self.open_position:
            return None
        in_price = self.open_position.price
        if in_price and self.session.last_price:
            return (self.session.last_price - in_price) * self.session.assets
        return None

    @property
    def open_position_delta_pct(self):
        if not self.open_position:
            return None
        in_price = self.open_position.price
        if not self.session.last_price or not in_price:
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
       
    @property
    def weighted_pnl_pct(self):
        """
        Calculate the weighted percentage profit or loss for the sell order.

        """
        sell_orders = self.orders.filter(side=Order.Side.SELL)
        weighted_pnl_sum =  [ order.pnl / order.deal_size for order in sell_orders if order.pnl and order.deal_size ]
        weighted_cost_sum = [ order.deal_size for order in sell_orders  if order.deal_size ]
        return sum(weighted_pnl_sum) * 100 / sum(weighted_cost_sum) if weighted_cost_sum else None

    @property
    def total_pnl(self):
        """
        Calculate the total profit or loss for the sell order.

        """
        orders = self.orders.filter(side=Order.Side.SELL)
        total_pnl_sum = [ order.pnl for order in orders if order.pnl ]
        return sum(total_pnl_sum) if total_pnl_sum else None

    @property
    def max_hold_time(self):
        """
        Calculate the maximum hold time for the session.

        """
        orders = self.orders
        max_hold_time = timedelta(seconds=0)
        in_position = False
        in_time = None
        hold_time = None
        for order in orders:
            if order.side == Order.Side.BUY:
                in_position = True
                in_time = order.created_at
            elif order.side == Order.Side.SELL and in_position:
                in_position = False
                out_time = order.created_at
                if out_time and in_time:
                    hold_time = out_time - in_time
    
                if not max_hold_time or (hold_time and hold_time > max_hold_time):
                    max_hold_time = hold_time
        return max_hold_time

class OrderAnalytics:

    def __init__(self, order:Order) -> None:
        self.order = order

    @property
    def average_cost(self):
        """
        Calculate the average cost of the buy order.        

        """
        if not self.order.session:
            return
        orders = self.order.session.orders.filter(status=Order.Status.FILLED)
        assets = 0

        orders_except_self = orders.exclude(pk=self.order.pk)
        for order in orders_except_self:
            if order.side == Order.Side.BUY:
                assets += order.deal_size
            elif order.side == Order.Side.SELL:
                assets -= order.deal_size

        if self.order.side != Order.Side.BUY:
            return

        
        avg_cost = (((self.last_average_cost or 0) * assets) + (self.order.price * self.order.deal_size)) / (assets + self.order.deal_size)
        return avg_cost

    @property
    def last_average_cost(self):
        if not self.order.session:
            return
        last_buy = self.order.session.orders.filter(status=Order.Status.FILLED, side=Order.Side.BUY)
        if self.order.side == Order.Side.BUY:
            last_buy = last_buy.exclude(pk=self.order.pk).last()
        else:
            last_buy = last_buy.last()
        if not last_buy:
            return
        return last_buy.average_cost

    @property
    def pnl(self):
        """
        Calculate the profit or loss for the sell order.

        """
        if self.order.side != Order.Side.SELL:
            return
        avg_cost = self.last_average_cost
        if not avg_cost or not self.order.price or not self.order.deal_size:
            return
        pnl = (self.order.price - avg_cost) * self.order.deal_size
        return pnl

    @property
    def pnl_pct(self):
        """
        Calculate the percentage profit or loss for the sell order.

        """
        if self.order.side != Order.Side.SELL:
            return
        avg_cost = self.last_average_cost
        if not avg_cost:
            return
        pnl_pct = (self.order.price - avg_cost) / avg_cost * 100
        return pnl_pct


class TotalSessionAnalytics:
    def __init__(self, sessions=None) -> None:
        self.sessions = sessions or Session.objects.filter(status=Session.Status.ONGOING)
        self.sessions = self.sessions.exclude(symbol__market__mainnet_enabled=False)
        self.market_analytics = MarketAnalytics()
    
    def capital(self):
        return sum([session.capital for session in self.sessions])
    
    def equity(self):
        return self.capital() + sum([session.assets * session.last_price for session in self.sessions if session.assets and session.last_price])
    
    def open_positions(self):
        # return the number of open positions for the sessions (i.e. last order was a BUY with status FILLED)
        count = 0
        for session in self.sessions:
            order = Order.objects.filter(signal__session=session, status=Order.Status.FILLED).last()
            if order and order.side == Order.Side.BUY:
                count += 1
        return count
    
    def count(self):
        return self.sessions.count()
    
    def equity_delta(self):
        initial_asset_value = sum([session.initial_assets * session.initial_price for session in self.sessions if session.initial_assets and session.initial_price])
        initial_total_value = sum([session.initial_capital + initial_asset_value for session in self.sessions])
        return self.equity() - initial_total_value
    
    def equity_delta_pct(self):
        try:
            return (self.equity_delta() / self.market_analytics.equity()) * 100
        except ZeroDivisionError:
            return None



class MarketAnalytics:
    def __init__(self):
        self.markets = Market.objects.filter(mainnet_enabled=True)

    def capital(self):
        return sum([market.usdt for market in self.markets if market.usdt])
    
    def equity(self):
        return sum([market.equity for market in self.markets if market.equity])
