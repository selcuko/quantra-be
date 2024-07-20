from datetime import datetime
import threading
from typing import Any, Callable, Optional
from orderpulse.structures import Book
from markets.interface import IMarket
from queue import Queue
import typing
if typing.TYPE_CHECKING:
    from quantapi.models import MarketSymbol


class KeeperPool:
    pool: dict['MarketSymbol', 'BookKeeper'] = {}

    @classmethod
    def get(cls, symbol:'MarketSymbol', callback:Optional[Callable]=None):
        if (keeper := cls.pool.get(symbol)):
            if callback and callback not in keeper.callbacks:
                keeper.add_callback(callback)
            return keeper
        keeper = BookKeeper(symbol, callback)
        cls.pool[symbol] = keeper
        return keeper


class BookKeeper:
    def __init__(self, symbol:'MarketSymbol', callback:Optional[Callable]=None, interface:Optional['IMarket']=None):
        self.interface = interface or symbol.market.get_interface()
        self.symbol = symbol
        self.callbacks = [callback] if callback else []
        self.name = f'BookKeeper of {symbol.name}@{self.interface.name}'
        self.market_thread = None
        self.process_thread = None
        self.book = Book()
        self.snapshot_applied = False
        self.market = symbol.market
        self.last_update = None
        self.started = False
        self.queue = Queue()
        self.stop_event = False

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
        self.process_thread = threading.Thread(target=self.process_queue, daemon=True)
        self.process_thread.start()

    def is_running(self):
        return self.market_thread and self.market_thread.is_alive() and self.process_thread and self.process_thread.is_alive()

    def on_snapshot(self, snapshot:dict):
        self.book.on_snapshot(snapshot)
        self.snapshot_applied = True

    def on_update(self, update:dict):
        update['received'] = datetime.now()
        self.queue.put(update)

    def process_queue(self):
        while not self.stop_event:
            update = self.queue.get()
            self.last_update = datetime.now()
            diff = self.process(update)
            for callback in self.callbacks:
                callback(diff)

    def process(self, update:dict):
        self.last_update = datetime.now()
        diff = self.book.on_update(update)
        return diff

    def add_callback(self, callback:Callable):
        if not callback in self.callbacks:
            self.callbacks.append(callback)

    def stop(self):
        self.stop_event = True
        if self.market_thread and self.market_thread.is_alive():
            self.interface.stop_websocket_stream = True
            self.market_thread.join()

    def since_last_update(self):
        return (datetime.now() - self.last_update).total_seconds() if self.last_update else None
