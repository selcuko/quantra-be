import copy
from datetime import datetime
from multiprocessing import Queue, synchronize
import multiprocessing
import threading
from orderpulse.manager import BookManager
from orderpulse.structures import Book
import typing
if typing.TYPE_CHECKING:
    from quantapi.models import MarketSymbol

class Keeper:
    def __init__(self, symbol:'MarketSymbol', manager:BookManager):
        self.symbol = symbol
        self.market = symbol.market.exchange_name
        self.interface = symbol.market.get_interface()
        self.manager = manager
        self.book = manager.create_book()
        self.update_queue = manager.Queue()
        self.dispatch_queue = manager.Queue()
        self.stop_event = manager.Event()
        self.book_lock = manager.Lock()
        self.received_seq = 0
        self.market_thread = None
        self.callbacks = []

    def add_callback(self, callback):
        """Adds a callback to the list of callbacks that will be called when an update is processed (callbacks are blocking, make them fast)"""
        self.callbacks.append(callback)

    def start(self):
        """Gets a snapshot from the exchange, starts the queue processor and the dispatcher"""
        with self.book_lock:
            snapshot = self.interface.get_full_orderbook(self.symbol)
            self.received_seq += 1
            snapshot['received'] = datetime.now()
            snapshot['market'] = self.symbol.market.exchange_name
            snapshot['sequence'] = self.received_seq
            delta = Book.convert(snapshot)
            Book.apply(self.book, delta)
        self.market_thread = threading.Thread(target=self.interface.init_orderbook_websocket, args=(self.symbol, self.on_update))
        self.market_thread.start()
        self.dispatch_thread = threading.Thread(target=self.dispatch)
        self.dispatch_thread.start()
        self.worker_process = multiprocessing.Process(target=Keeper.worker, args=(self.book, self.update_queue, self.dispatch_queue, self.stop_event, self.book_lock))
        self.worker_process.start()

    def on_update(self, update:dict):
        """Receives an update from the exchange, adds metadata and queues it for processing"""
        update['received'] = datetime.now()
        update['market'] = self.market
        self.received_seq += 1
        update['sequence'] = self.received_seq
        delta = Book.convert(update)
        delta.market = self.market
        self.update_queue.put(delta)

    @staticmethod
    def worker(book: Book, queue: Queue, dispatch: Queue, stop_event: synchronize.Event, lock: synchronize.Lock):
        """Processes the updates from the queue and applies them to the book"""
        while not stop_event.is_set():
            with lock:
                delta = queue.get()
                diff_delta = Book.insert(book, delta)
                diff_delta.processed = datetime.now()
                dispatch.put(diff_delta)

    def dispatch(self):
        """Dispatches the processed updates to the database"""
        while not self.stop_event.is_set():
            delta = self.dispatch_queue.get()
            for callback in self.callbacks:
                callback(delta)

    def snapshot(self) -> Book:
        """Freeze the book and return a snapshot."""
        with self.book_lock:
            return self.manager.create_book(
                bids=copy.deepcopy(self.book.bids),
                asks=copy.deepcopy(self.book.asks),
                seq=self.book.sequence.value
            )

    def stop(self):
        """Stops the market thread and the worker process"""
        self.interface.stop_websocket_stream = True
        self.stop_event.set()
        if self.market_thread: self.market_thread.join()
        self.worker_process.join()
        self.manager.shutdown()
