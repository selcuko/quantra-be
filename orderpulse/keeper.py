import copy
from datetime import datetime
from multiprocessing import Queue, synchronize
import multiprocessing
import threading
import time
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
        self.last_update = None
        self.last_processed_ts = manager.Value('i', 0)
        self.received_seq = 0
        self.market_thread = None
        self.callbacks = []
        self.worker_process = None
        self.dispatch_thread = None
        self.market_thread = None

    def state(self):
        status = 'undefined'
        qsize = self.update_queue.qsize()
        dispatch = self.dispatch_queue.qsize()
        updates = self.received_seq
        latency_from = datetime.fromtimestamp(self.last_processed_ts.value) if self.last_processed_ts.value else None
        latency_to = self.last_update
        latency_sec = (latency_to - latency_from).total_seconds() if latency_from and latency_to else None
        since_last_update = f'{latency_sec:.3f}s' if latency_sec else 'never'
        if self.received_seq == 0:
            status = 'waiting snapshot'
        if self.received_seq == 1:
            status = 'subscribing to ws'
        elif self.market_thread and self.market_thread.is_alive() and self.worker_process and self.worker_process.is_alive() and self.dispatch_thread and self.dispatch_thread.is_alive():
            status = 'running'
        else:
            status = 'degraded'
        return f'{status} [{since_last_update}] [Q:{qsize} D:{dispatch} U:{updates}]'


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
        self.worker_process = multiprocessing.Process(target=Keeper.worker, args=(self.book, self.update_queue, self.dispatch_queue, self.stop_event, self.book_lock, self.last_processed_ts))
        self.worker_process.start()

    def on_update(self, update:dict):
        """Receives an update from the exchange, adds metadata and queues it for processing"""
        update['received'] = datetime.now()
        update['market'] = self.market
        self.received_seq += 1
        self.last_update = datetime.now()
        update['sequence'] = self.received_seq
        self.update_queue.put(update)

    @staticmethod
    def worker(book: Book, queue: Queue, dispatch: Queue, stop_event: synchronize.Event, lock: synchronize.Lock, last_ts):
        """Processes the updates from the queue and applies them to the book"""
        while not stop_event.is_set():
            with lock:
                update = queue.get()
                delta = Book.convert(update)
                diff_delta = Book.insert(book, delta)
                diff_delta.processed = datetime.now()
                dispatch.put(diff_delta)
                last_ts.value = int(delta.received.timestamp())

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
        if self.market_thread: 
            self.market_thread.join()
        if self.worker_process: 
            self.worker_process.join()
        if self.dispatch_thread:
            self.dispatch_thread.join()
        self.manager.shutdown()
