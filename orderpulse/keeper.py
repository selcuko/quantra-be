import multiprocessing
import multiprocessing.synchronize
import threading
import time
import typing
from datetime import datetime
from multiprocessing.sharedctypes import Synchronized
from multiprocessing.synchronize import Event as EventClass
from typing import Callable, Optional

from sortedcontainers import SortedDict

from markets.interface import IMarket
from orderpulse.manager import BookManager
from orderpulse.structures import Book

if typing.TYPE_CHECKING:
    from quantapi.models import MarketSymbol


def queue_worker(bids: SortedDict, asks: SortedDict, queue:multiprocessing.Queue, last_update:'Synchronized[int]', stop_event:EventClass):
    while not stop_event.is_set():
        update = queue.get()
        Book.on_update(bids, asks, update)
        last_update.value = int(time.time())


class KeeperPool:
    pool: dict['MarketSymbol', 'BookKeeper'] = {}
    manager = BookManager()
    manager_started = False

    @classmethod
    def get(cls, symbol:'MarketSymbol', callback:Optional[Callable]=None):
        if not cls.manager_started:
            cls.manager.start()
            cls.manager_started = True
        if (keeper := cls.pool.get(symbol)):
            if callback and callback not in keeper.callbacks:
                keeper.add_callback(callback)
            return keeper
        keeper = BookKeeper(symbol, cls.manager, callback)
        cls.pool[symbol] = keeper
        return keeper


class BookKeeper:
    def __init__(self, symbol:'MarketSymbol', manager: BookManager, callback:Optional[Callable]=None, interface:Optional['IMarket']=None):
        self.interface = interface or symbol.market.get_interface()
        self.symbol = symbol
        self.callbacks = [callback] if callback else []
        self.name = f'BookKeeper of {symbol.name}@{self.interface.name}'
        self.market_thread = None
        self.process_thread = None
        self.snapshot_applied = False
        self.market = symbol.market
        self.last_update = manager.Value('i', 0)
        self.started = False
        self.queue = manager.Queue()
        self.stop_event = multiprocessing.Event()
        self.update_count = 0
        self.book = Book(manager)

    @property
    def state(self):
        if not self.started:
            return 'initialized'
        if not self.snapshot_applied:
            return 'snapshot'
        if self.is_running():
            td = self.since_last_update()
            if not td:
                return f'running [no updates][Q:{self.queue.qsize()}]'
            if td == 0:
                return f'running [just now][Q:{self.queue.qsize()}]'
            return f'running [{td:.2f}s][Q:{self.queue.qsize()}]'
        return 'stopped'

    def __str__(self):
        return self.name

    def start(self):
        if self.is_running():
            return
        self.started = True
        snapshot = self.interface.get_full_orderbook(self.symbol)
        self.on_snapshot(snapshot)
        self.market_thread = threading.Thread(target=self.interface.init_orderbook_websocket, args=(self.symbol, self.on_update), daemon=True)
        self.market_thread.start()
        self.process_queue()

    def is_running(self):
        return self.market_thread and self.market_thread.is_alive()

    def on_snapshot(self, snapshot:dict):
        self.book.on_snapshot(snapshot)
        self.snapshot_applied = True

    def on_update(self, update:dict):
        update['received'] = datetime.now()
        self.queue.put(update)
        self.update_count += 1

    def process_queue(self):
        proc = multiprocessing.Process(target=queue_worker, args=(self.book.bids, self.book.asks, self.queue, self.last_update, self.stop_event), daemon=True)
        proc.start()

    def add_callback(self, callback:Callable):
        if not callback in self.callbacks:
            self.callbacks.append(callback)

    def stop(self):
        self.stop_event.set()
        if self.market_thread and self.market_thread.is_alive():
            self.interface.stop_websocket_stream = True
            self.market_thread.join()

    def since_last_update(self):
        updated = datetime.fromtimestamp(self.last_update.value)
        return (datetime.now() - updated).total_seconds() if self.last_update else None
