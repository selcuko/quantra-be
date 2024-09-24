from datetime import datetime
from decimal import Decimal
from threading import Event, Thread, Timer
import time
from typing import Callable, TYPE_CHECKING
from markets.interface import IMarket
from orderpulse.keeper import Keeper, KeeperPool
from orderpulse.structures import Delta
from asgiref.sync import async_to_sync
if TYPE_CHECKING:
    from quantapi.models import Market, MarketSymbol


KEEP_ALIVE = [
    'BTC-USDT BINANCE-SPOT',
    'BTC-USDT BINANCE-FUTURES',
]

KEEP_ALIVE_TICKERS = [
    'btc-usdt.binance.spot.1min',
    'btc-usdt.binance.futures.1min',
]


def bucket(price:float):
    x = None
    if price < 0.001:
        x = 0.00001
    if 0.01 < price < 0.1:
        x = 0.0001
    if 0.1 < price < 1:
        x = 0.001
    if 1 < price < 10:
        x = 0.01
    if 10 < price < 100:
        x = 0.1
    if 100 < price < 1000:
        x = 1
    if 1000 < price < 10000:
        x = 10
    if 10000 < price:
        x = 100
    return Decimal(x or 1)

def bucket_l2(price:Decimal, divisor:Decimal):
    return price / divisor


class KeeperDispatch:
    """Manages the relation between the Consumers and the Keepers."""
    def __init__(self):
        from channels.layers import get_channel_layer
        self.channels: dict[Keeper, dict[str, list[str]]] = {}  # maps group names to keepers, basically groups depths (buckets)
        self.connections: dict[Keeper, list[str]] = {}          # dict of Keeper: channel_name: [connection_ids]
        self.callbacks: dict[Keeper, Callable[[Delta], None]] = {}
        self.last_updates: dict[Keeper, datetime] = {}
        self.channel_layer = get_channel_layer()
        self.holdback_secs = 1
        self.shutdown_countdown = 60
        self.shutdown_schedules: dict[Keeper, Timer] = {}

    def make_callback(self, keeper: Keeper) -> Callable[[Delta], None]:
        """Creates a callback function for the given Keeper."""
        if keeper in self.callbacks:
            return self.callbacks[keeper]
        def callback(delta: Delta):
            assert self.channel_layer, 'Channel layer is not available'
            if not self.last_updates.get(keeper):
                self.last_updates[keeper] = datetime.now()
            elif (datetime.now() - self.last_updates[keeper]).seconds < self.holdback_secs:
                return
            self.last_updates[keeper] = datetime.now()
            channels = list(self.channels[keeper].keys())
            for channel in channels:
                channel_depth = channel.split('.')[-1]
                if channel_depth == 'default':
                    best_bid_price = float(keeper.book.get_best(count=1)[0][0].price)
                    bucket_precision = bucket(best_bid_price)
                    depth = bucket_l2(bucket_precision, Decimal(10))
                else:
                    depth = Decimal(channel_depth)
                bids, asks = keeper.book.get_depth(200, depth)
                payload = {
                    'bids': [bid.dict() for bid in bids],
                    'asks': [ask.dict() for ask in asks],
                    'price': keeper.book.get_price(),
                    'type': 'update',
                }
                async_to_sync(self.channel_layer.group_send)(channel, payload)
        self.callbacks[keeper] = callback
        return callback

    def get(self, connection_id: str, symbol: 'MarketSymbol') -> Keeper:
        """Returns the corresponding Keeper for the given MarketSymbol from the pool or creates a new one."""
        keeper = KeeperPool.get(symbol)
        keeper.add_callback(self.make_callback(keeper))
        self.connections.setdefault(keeper, []).append(connection_id)
        self.channels.setdefault(keeper, {}).setdefault(keeper.key+'.default', []).append(connection_id)
        self.cancel_keeper_shutdown(keeper)
        return keeper

    def drop(self, connection_id: str, keeper: Keeper|None):
        """Lets the Dispatch know that a connection has been dropped."""
        if not keeper:
            keeper = self.find_keeper_for_connection(connection_id)
        if not keeper:
            return
        keeper_connections = self.connections[keeper]
        keeper_connections.remove(connection_id)
        keeper_channels = self.channels[keeper]
        channels_to_remove = []
        for channel_name, connections in keeper_channels.items():
            if connection_id in connections:
                connections.remove(connection_id)
                if not connections:
                    channels_to_remove.append(channel_name)
        for channel_name in channels_to_remove:
            del keeper_channels[channel_name]
        should_drop_keeper = True
        if keeper and str(keeper.symbol) in KEEP_ALIVE:
            should_drop_keeper = False
        if not keeper_connections and should_drop_keeper:
            if keeper in self.callbacks:
                del self.callbacks[keeper]
            del self.connections[keeper]
            self.schedule_keeper_shutdown(keeper)

    def update_depth(self, connection_id:str, old_channel_name:str, new_channel_name:str):
        keeper = self.find_keeper_for_connection(connection_id)
        if not keeper:
            return
        keeper_channels = self.channels[keeper]
        if new_channel_name in keeper_channels:
            keeper_channels[new_channel_name].append(connection_id)
        else:
            keeper_channels[new_channel_name] = [connection_id]
        if old_channel_name in keeper_channels:
            keeper_channels[old_channel_name].remove(connection_id)
            if not keeper_channels[old_channel_name]:
                del keeper_channels[old_channel_name]

    def schedule_keeper_shutdown(self, keeper: Keeper):
        """Schedules a Keeper for shutdown."""
        if keeper in self.shutdown_schedules:
            return
        timer = Timer(self.shutdown_countdown, self.drop_keeper, args=[keeper])
        self.shutdown_schedules[keeper] = timer
        timer.start()

    def cancel_keeper_shutdown(self, keeper: Keeper):
        """Cancels the scheduled shutdown of a Keeper."""
        if keeper not in self.shutdown_schedules:
            return
        self.shutdown_schedules[keeper].cancel()
        del self.shutdown_schedules[keeper]

    def find_keeper_for_connection(self, connection_id: str) -> Keeper|None:
        keeper = None
        for k, v in self.connections.items():
            if connection_id in v:
                keeper = k
                break
        return keeper

    @staticmethod
    def drop_keeper(keeper: Keeper):
        KeeperPool.pop(keeper)

    @staticmethod
    def drop_keeper_with_symbol(symbol: 'MarketSymbol'):
        def in_thread():
            KeeperPool.pop_symbol(symbol)
        Thread(target=in_thread).start()
        return True


class TickerDispatch:
    """Manages the relation between the Consumers and Tickers."""
    def __init__(self):
        from channels.layers import get_channel_layer
        self.threads: dict['str', Thread] = {}
        self.connections: dict['str', list[str]] = {}
        self.callbacks: dict['str', Callable[[dict], None]] = {}
        self.last_updates: dict['str', datetime] = {}
        self.channel_layer = get_channel_layer()
        self.holdback_secs = 0
        self.shutdown_countdown = 1
        self.shutdown_schedules: dict['str', Timer] = {}
        self.interfaces: dict[Market, IMarket] = {}
        self.stop_events: dict['str', Event] = {}

    def make_callback(self, symbol: 'MarketSymbol', interval: str) -> Callable[[dict], None]:
        """Creates a callback function for the given MarketSymbol."""
        key = f'{symbol.key()}.{interval}'
        if key in self.callbacks:
            return self.callbacks[key]
        def callback(payload: dict):
            assert self.channel_layer, 'Channel layer is not available'
            if not self.last_updates.get(key):
                self.last_updates[key] = datetime.now()
            elif (datetime.now() - self.last_updates[key]).seconds < self.holdback_secs:
                return
            self.last_updates[key] = datetime.now()
            payload['type'] = 'update'
            group_name = key.replace(' ', '')
            async_to_sync(self.channel_layer.group_send)(group_name, payload)
        self.callbacks[key] = callback
        return callback

    def get_interface(self, market: 'Market') -> IMarket:
        """Returns the corresponding IMarket for the given Market from the pool or creates a new one."""
        if market in self.interfaces:
            return self.interfaces[market]
        interface = market.get_interface()
        self.interfaces[market] = interface
        return interface

    def start_thread(self, symbol: 'MarketSymbol', interval: str):
        key = f'{symbol.key()}.{interval}'
        if key in self.threads:
            return self.threads[key]
        interface = self.get_interface(symbol.market)
        stop_event = Event()
        thread = Thread(
            target=interface.init_match_engine, 
            args=[symbol, interval, self.make_callback(symbol, interval), stop_event, None, self.make_callback(symbol, interval)]
        )
        self.threads[key] = thread
        self.stop_events[key] = stop_event
        thread.start()
        return thread

    def restart_thread(self, symbol: 'MarketSymbol', interval: str):
        key = f'{symbol.key()}.{interval}'
        thread = self.threads.get(key)
        if not thread:
            return self.start_thread(symbol, interval)
        thread.join()
        while thread.is_alive():
            time.sleep(0.1)
        return self.start_thread(symbol, interval)

    def get(self, connection_id: str, symbol: 'MarketSymbol', interval: str):
        """Returns the corresponding Keeper for the given MarketSymbol from the pool or creates a new one."""
        self.start_thread(symbol, interval)
        key = f'{symbol.key()}.{interval}'
        self.connections.setdefault(key, []).append(connection_id)
        self.cancel_ticker_shutdown(key)

    def drop(self, connection_id: str, symbol: 'MarketSymbol|None', interval: str):
        """Lets the Dispatch know that a connection has been dropped."""
        if not symbol:
            key = self.find_ticker_for_connection(connection_id)
        else:
            key = f'{symbol.key()}.{interval}'
        if not key:
            return
        if key not in self.connections:
            return
        ticker_connections = self.connections[key]
        ticker_connections.remove(connection_id)
        should_drop_ticker = True
        if key in KEEP_ALIVE_TICKERS:   
            should_drop_ticker = False
        if not ticker_connections and should_drop_ticker:
            if symbol in self.callbacks:
                del self.callbacks[key]
            del self.connections[key]
            self.schedule_ticker_shutdown(key)

    def schedule_ticker_shutdown(self, key: str):
        """Schedules a Ticker for shutdown."""
        if key in self.shutdown_schedules:
            return
        timer = Timer(self.shutdown_countdown, self.drop_ticker, args=[key])
        self.shutdown_schedules[key] = timer
        timer.start()

    def cancel_ticker_shutdown(self, key: str):
        """Cancels the scheduled shutdown of a Ticker."""
        if key not in self.shutdown_schedules:
            return
        self.shutdown_schedules[key].cancel()
        del self.shutdown_schedules[key]

    def find_ticker_for_connection(self, connection_id: str) -> 'str|None':
        ms = None
        for k, v in self.connections.items():
            if connection_id in v:
                ms = k
                break
        return ms

    def drop_ticker(self, key: str):
        event = self.stop_events.get(key)
        if not event:
            return
        event.set()
        del self.stop_events[key]
        del self.threads[key]
