from multiprocessing import Queue, synchronize
import multiprocessing
import threading
from orderpulse.keeper import Keeper, KeeperPool
from orderpulse.manager import BookManager
from orderpulse.structures import Book, Delta


class AggregatorPool:
    pool: dict[int, 'Aggregator'] = {}
    manager = BookManager()
    manager_started = False

    @classmethod
    def get(cls, symbol:str, markets: list[str], futures=False) -> 'Aggregator':
        if not cls.manager_started:
            cls.manager.start()
            cls.manager_started = True
        unique = hash('+'.join(markets))
        if not unique in cls.pool:
            aggregator = Aggregator(symbol, cls.manager, futures=futures)
            aggregator.add_markets(markets)
            cls.pool[unique] = aggregator
        return cls.pool[unique]

    @classmethod
    def pop(cls, aggregator: 'Aggregator'):
        unique = hash('+'.join(aggregator.keepers.keys()))
        cls.pool.pop(unique)
        if not cls.pool and cls.manager_started:
            cls.manager.shutdown()
            cls.manager_started = False


class Aggregator:
    def __init__(self, symbol: str, manager: BookManager, futures=False):
        self.symbol = symbol
        self.manager = manager
        self.book = manager.create_book()
        self.keepers:dict[str, Keeper] = {}
        self.update_queue = manager.Queue()
        self.stop_event = manager.Event()
        self.buffers:dict[str, list[Delta]] = {}
        self.recv_seq:dict[str, int] = {}
        self.queue_processor = multiprocessing.Process(target=Aggregator.worker, args=(self.book, self.update_queue, self.stop_event))
        self.queue_processor.start()
        self.callbacks = []
        self.futures = futures
        self.contract_type = 'FUTURES' if futures else 'SPOT'

    def __hash__(self):
        unique = '+'.join(self.keepers.keys())
        return hash(unique)

    def add_callback(self, callback):
        self.callbacks.append(callback)

    def remove_callback(self, callback):
        self.callbacks.remove(callback)

    def add_markets(self, names: list[str]):
        def wrapped():
            for name in names:
                self.add_market(name)
        threading.Thread(target=wrapped).start()

    def add_market(self, name: str):
        from quantapi.models import Market, MarketSymbol
        market = Market.objects.get(exchange_name=name)
        symbol = MarketSymbol.objects.get(contract_type=self.contract_type, market=market, name=self.symbol)
        keeper = KeeperPool.get(symbol)
        self.add_keeper(keeper)

    def add_keeper(self, keeper: Keeper):
        keeper.add_callback(self.keeper_callback)
        snapshot = keeper.snapshot()
        Book.merge(self.book, snapshot)
        self.recv_seq[keeper.market] = snapshot.sequence.value
        self.keepers[keeper.market] = keeper

    def keeper_callback(self, delta: Delta, exhaust=False):
        if not exhaust and not delta.market in self.keepers:
            if not delta.market in self.buffers:
                self.buffers[delta.market] = []
            self.buffers[delta.market].append(delta)
            return
        if not exhaust and self.buffers.get(delta.market):
            while self.buffers[delta.market] and (b := self.buffers[delta.market].pop(0)):
                self.keeper_callback(b, exhaust=True)
        if delta.sequence <= self.recv_seq.get(delta.market, -1):
            return
        self.recv_seq[delta.market] = delta.sequence
        self.update_queue.put(delta)
        for callback in self.callbacks:
            callback(delta)

    @staticmethod
    def worker(book: Book, queue: Queue, stop_event: synchronize.Event):
        while not stop_event.is_set():
            delta = queue.get()
            delta.sequence = book.sequence.value + 1
            Book.apply(book, delta)

    def get_price(self) -> float:
        keeper_prices = [k.book.get_price() for k in self.keepers.values()]
        if not keeper_prices:
            return 0
        return float(sum(keeper_prices) / len(keeper_prices))

    def stop(self):
        self.stop_event.set()
        threads = []
        for keeper in self.keepers.values():
            stop_thread = threading.Thread(target=keeper.stop)
            stop_thread.start()
            threads.append(stop_thread)
        self.queue_processor.join()
        for thread in threads:
            thread.join()
        AggregatorPool.pop(self)
