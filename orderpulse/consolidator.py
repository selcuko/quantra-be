from threading import Thread
from orderpulse.keeper import BookKeeper, KeeperPool
from orderpulse.structures import Bid, Book
from quantapi.models import MarketSymbol, Market


class BookAggregator:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.book = Book()
        self.keepers: dict[str, BookKeeper] = {}
        self.px_in_process = []

    def add_markets(self, markets: list[str]):
        def inner(market):
            for market in markets:
                self.add_market(market)
        Thread(target=inner, args=(markets,), daemon=True).start()

    def add_market(self, market: str):
        symbol = MarketSymbol.objects.get(name=self.symbol, market=Market.objects.get(exchange_name=market))
        keeper = KeeperPool.get(symbol, self.keeper_callback)
        Thread(target=self.add_keeper, args=(keeper,), daemon=True).start()

    def add_keeper(self, keeper: BookKeeper, start=True):
        self.keepers[keeper.interface.name] = keeper
        if not keeper.snapshot_applied:
            if not start:
                raise ValueError('Cannot add keeper without applying snapshot (set start=True to apply snapshot automatically)')
            keeper.start()
        self.keeper_snapshot(keeper)
        keeper.add_callback(self.keeper_callback)

    def keeper_snapshot(self, keeper):
        for bid in keeper.book.bids.values():
            self.calc_price_point(bid.price, 'bids')
        for ask in keeper.book.asks.values():
            self.calc_price_point(ask.price, 'asks')

    def keeper_callback(self, update):
        for bid in update.get('bids', []):
            bid = Bid(bid.get('price'), bid.get('size'), bid.get('updated'))
            if bid.size == 0:
                pass
            self.calc_price_point(bid.price, 'bids')
        for ask in update.get('asks', []):
            ask = Bid(ask.get('price'), ask.get('size'), ask.get('updated'))
            self.calc_price_point(ask.price, 'asks')

    def calc_price_point(self, px: float, side='bids'):
        if px in self.px_in_process:
            return
        self.px_in_process.append(px)
        bids = []
        container = self.book.bids if side == 'bids' else self.book.asks
        for keeper in self.keepers.values():
            keeper_container = keeper.book.bids if side == 'bids' else keeper.book.asks
            if (b := keeper_container.get(px)):
                bids.append(b)
        if not bids:
            container.pop(px, None)
            return
        merged_bid = self.merge_bids(bids)
        if merged_bid.size == 0:
            container.pop(merged_bid.price, None)
        else:
            self.book.insert_bid(merged_bid, side, clean=False)
        self.px_in_process.remove(px)

    def merge_bids(self, bids:list[Bid]):
        if len(bids) == 0:
            raise ValueError('Cannot merge zero bids')
        if len(bids) == 1:
            return bids[0]
        if len({ bid.price for bid in bids }) > 1:
            raise ValueError('Cannot merge bids with different prices')
        bid = Bid(
            price=bids[0].price,
            size=sum(b.size for b in bids),
            updated=max(b.updated for b in bids)
        )
        return bid

    def get_price(self):
        def calc_keeper_weight(keeper):
            return sum(b.value for b in keeper.book.bids.values()) + sum(a.value for a in keeper.book.asks.values())
        total_weight = sum(calc_keeper_weight(keeper) for keeper in self.keepers.values())
        if total_weight == 0:
            return 0
        return sum(keeper.book.get_price() * calc_keeper_weight(keeper) / total_weight for keeper in self.keepers.values())
