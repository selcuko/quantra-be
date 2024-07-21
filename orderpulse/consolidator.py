import multiprocessing
from multiprocessing.managers import ListProxy
import multiprocessing.synchronize
from threading import Thread
import time

from sortedcontainers import SortedDict
from orderpulse.keeper import BookKeeper, KeeperPool
from orderpulse.locks import ReadWriteLock
from orderpulse.manager import BookManager
from orderpulse.structures import Bid, Book


class AggregatorPool:
    pool: dict[int, 'BookAggregator'] = {}
    manager = BookManager()
    manager_started = False

    @classmethod
    def get(cls, symbol:str, markets: list[str]):
        if (aggregator := cls.pool.get(hash('+'.join(markets)))):
            return aggregator
        return cls.new(symbol, markets)

    @classmethod
    def new(cls, symbol:str, markets: list[str]):
        if not cls.manager_started:
            cls.manager.start()
            cls.manager_started = True
        aggregator = BookAggregator(symbol, cls.manager)
        aggregator.add_markets(markets)
        cls.set(aggregator)
        return aggregator

    @classmethod
    def set(cls, aggregator: 'BookAggregator'):
        cls.pool[aggregator.hash()] = aggregator


class BookAggregator:
    def __init__(self, symbol: str, manager: BookManager):
        self.symbol = symbol
        self.book = Book(manager)
        self.keepers: dict[str, BookKeeper] = {}
        self.applied_snapshots: list[str] = []
        self.px_in_process = manager.list()
        self.workers = multiprocessing.Pool(processes=6)
        self.rwlock = ReadWriteLock(manager)
        self.queue = manager.Queue()
        self.updates_count = 0
        self.qsize = manager.Value('i', 0)

    def hash(self):
        return hash('+'.join(self.keepers.keys()))

    def add_markets(self, markets: list[str]):
        def inner(market):
            for market in markets:
                try:
                    self.add_market(market)
                except Exception as e:
                    print('ERROR ADDING MARKET', market, e)
        Thread(target=inner, args=(markets,), daemon=True).start()

    def add_market(self, market: str):
        from quantapi.models import MarketSymbol, Market
        symbol = MarketSymbol.objects.get(name=self.symbol, market=Market.objects.get(exchange_name=market))
        keeper = KeeperPool.get(symbol)
        Thread(target=self.add_keeper, args=(keeper,), daemon=True).start()

    def add_keeper(self, keeper: BookKeeper, start=True):
        #print('ADDING', keeper.interface.name)
        with self.rwlock.write():
            self.keepers[keeper.interface.name] = keeper
        if not keeper.snapshot_applied:
            if not start:
                raise ValueError('Cannot add keeper without applying snapshot (set start=True to apply snapshot automatically)')
            keeper.start()
        with self.rwlock.read():
            keepers = { k.market.exchange_name: { 'bids': k.book.bids, 'asks': k.book.asks } for k in self.keepers.values() }
        self.qsize.value += 1
        self.workers.apply_async(self.keeper_snapshot, args=(self.book.bids, self.book.asks, keeper.book.bids.values(), keeper.book.asks.values(), self.px_in_process, keepers, self.rwlock, self.qsize))
        #BookAggregator.keeper_snapshot(self.book.bids, self.book.asks, keeper.book.bids.values(), keeper.book.asks.values(), self.px_in_process)
        keeper.add_callback(self.keeper_callback_async)

    @staticmethod
    def keeper_snapshot(bids: SortedDict, asks: SortedDict, keeper_bids: list[Bid], keeper_asks: list[Bid], px_in_process: ListProxy, keepers: dict[str, dict[str, SortedDict]], rwlock, qsize):
        for bid in keeper_bids:
            BookAggregator.calc_price_point(bids, asks, bid.price, px_in_process, 'bids', keepers, rwlock)
        for ask in keeper_asks:
            BookAggregator.calc_price_point(bids, asks, ask.price, px_in_process, 'asks', keepers, rwlock)
        qsize.value -= 1

    def keeper_callback_async(self, update):
        self.updates_count += 1
        self.qsize.value += 1
        keepers = { k.market.exchange_name: { 'bids': k.book.bids, 'asks': k.book.asks } for k in self.keepers.values() }
        self.workers.apply_async(self.keeper_callback, args=(self.book.bids, self.book.asks, update, self.px_in_process, keepers, self.rwlock, self.qsize))

    @staticmethod
    def keeper_callback(bids, asks, update, px_in_process, keepers: dict[str, dict[str, SortedDict]], rwlock, qsize):
        t0 = time.time()
        for bid in update.get('bids', []):
            bid = Bid(bid.get('price'), bid.get('size'), bid.get('updated'))
            if bid.size == 0:
                pass
            BookAggregator.calc_price_point(bids, asks, bid.price, px_in_process, 'bids', keepers, rwlock)
        for ask in update.get('asks', []):
            ask = Bid(ask.get('price'), ask.get('size'), ask.get('updated'))
            BookAggregator.calc_price_point(bids, asks, ask.price, px_in_process, 'asks', keepers, rwlock)
        t1 = time.time()
        #print(f'{t1-t0:.4f}')
        qsize.value -= 1

    @staticmethod
    def calc_price_point(__bids: SortedDict, __asks: SortedDict, px: float, px_in_process: ListProxy, side:str, keepers: dict[str, dict[str, SortedDict]], rwlock):
        t0 = time.time()
        if not keepers:
            print('NO KEEPERS SKIPPING')
            return
        if px in px_in_process or -px in px_in_process:
            return
        t1 = time.time()
        #print('CALCULATING PX', px)
        px_in_process.append(-px if side == 'bids' else px)
        new_bids = []
        container = __bids if side == 'bids' else __asks
        #print('WAITING FOR LOCK', keepers.keys())
        """for market, keeper_book in keepers.items():
            #print('COLLECTING BIDS', market)
            keeper_container = keeper_book['bids'] if side == 'bids' else keeper_book['asks']
            if (b := keeper_container.get(px)):
                new_bids.append(b)"""
        # as a list comprehension
        new_bids = [ keeper_container[px] for keeper_container in (keeper_book['bids'] if side == 'bids' else keeper_book['asks'] for keeper_book in keepers.values()) if keeper_container.get(px) ]
        t2 = time.time()
        if not new_bids:
            container.pop(px, None)
            px_in_process.remove(-px if side == 'bids' else px)
            #print('PX REMOVED', px)
            return
        t3 = time.time()
        #print('MERGING BIDS', len(new_bids))
        merged_bid = BookAggregator.merge_bids(new_bids)
        if merged_bid.size == 0:
            container.pop(merged_bid.price, None)
        else:
            Book.insert_bid(__bids, __asks, merged_bid, side, clean=False)
        t4 = time.time()
        px_in_process.remove(-px if side == 'bids' else px)
        #print('PX CALCULATED', px)
        #print(f'{t4-t3:.6f} - {t3-t2:.6f} - {t2-t1:.6f} - {t1-t0:.6f}')

    @staticmethod
    def merge_bids(bids:list[Bid]):
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
        with self.rwlock.read():
            total_weight = sum(calc_keeper_weight(keeper) for keeper in self.keepers.values())
            if total_weight == 0:
                return 0
            return sum(keeper.book.get_price() * calc_keeper_weight(keeper) / total_weight for keeper in self.keepers.values())

    def stop(self):
        with self.rwlock.read():
            for keeper in self.keepers.values():
                keeper.stop()
