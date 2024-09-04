from datetime import datetime
import threading
from typing import Callable, TYPE_CHECKING
from channels.layers import get_channel_layer
from orderpulse.keeper import Keeper, KeeperPool
from orderpulse.structures import Delta
from asgiref.sync import async_to_sync
if TYPE_CHECKING:
    from quantapi.models import MarketSymbol


KEEP_ALIVE = [
    'BTC-USDT BINANCE-SPOT',
    'BTC-USDT BINANCE-FUTURES',
]


class KeeperDispatch:
    """Manages the relation between the Consumers and the Keepers."""
    def __init__(self):
        self.connections: dict[Keeper, list[str]] = {}
        self.callbacks: dict[Keeper, Callable[[Delta], None]] = {}
        self.last_updates: dict[Keeper, datetime] = {}
        self.channel_layer = get_channel_layer()
        self.holdback_secs = 1
        self.shutdown_countdown = 60
        self.shutdown_schedules: dict[Keeper, threading.Timer] = {}

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
            bids, asks = keeper.book.get_depth(10)
            payload = {
                'bids': [bid.dict() for bid in bids],
                'asks': [ask.dict() for ask in asks],
                'price': keeper.book.get_price(),
                'type': 'update',
            }
            async_to_sync(self.channel_layer.group_send)(keeper.key, payload)
        self.callbacks[keeper] = callback
        return callback

    def get(self, connection_id: str, symbol: 'MarketSymbol') -> Keeper:
        """Returns the corresponding Keeper for the given MarketSymbol from the pool or creates a new one."""
        keeper = KeeperPool.get(symbol)
        keeper.add_callback(self.make_callback(keeper))
        self.connections.setdefault(keeper, []).append(connection_id)
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
        should_drop_keeper = True
        if keeper and str(keeper.symbol) in KEEP_ALIVE:
            should_drop_keeper = False
        if not keeper_connections and should_drop_keeper:
            if keeper in self.callbacks:
                del self.callbacks[keeper]
            del self.connections[keeper]
            self.schedule_keeper_shutdown(keeper)

    def schedule_keeper_shutdown(self, keeper: Keeper):
        """Schedules a Keeper for shutdown."""
        if keeper in self.shutdown_schedules:
            return
        timer = threading.Timer(self.shutdown_countdown, self.drop_keeper, args=[keeper])
        self.shutdown_schedules[keeper] = timer
        timer.start()

    def cancel_keeper_shutdown(self, keeper: Keeper):
        """Cancels the scheduled shutdown of a Keeper."""
        if keeper not in self.shutdown_schedules:
            return
        self.shutdown_schedules[keeper].cancel()
        del self.shutdown_schedules[keeper]

    def find_keeper_for_connection(self, connection_id: str) -> Keeper|None:
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
        threading.Thread(target=in_thread).start()
        return True
