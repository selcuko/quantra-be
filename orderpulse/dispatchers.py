from datetime import datetime
from typing import Callable, TYPE_CHECKING
from channels.layers import get_channel_layer
from orderpulse.keeper import Keeper, KeeperPool
from orderpulse.structures import Delta
from orderpulse.tasks import drop_connection
from asgiref.sync import async_to_sync
if TYPE_CHECKING:
    from quantapi.models import MarketSymbol


class KeeperDispatch:
    """Manages the relation between the Consumers and the Keepers."""
    def __init__(self):
        self.connections: dict[Keeper, list[str]] = {}
        self.callbacks: dict[Keeper, Callable[[Delta], None]] = {}
        self.last_updates: dict[Keeper, datetime] = {}
        self.channel_layer = get_channel_layer()
        self.holdback_secs = 1

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
        print('Getting keeper for', symbol)
        keeper = KeeperPool.get(symbol)
        keeper.add_callback(self.make_callback(keeper))
        self.connections.setdefault(keeper, []).append(connection_id)
        print('Connections:', self.connections)
        return keeper

    def drop(self, connection_id: str, keeper: Keeper|None):
        drop_connection(connection_id, self, keeper)

