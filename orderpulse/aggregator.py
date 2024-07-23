from multiprocessing import Queue, synchronize
import multiprocessing
from orderpulse.keeper import Keeper
from orderpulse.manager import BookManager
from orderpulse.structures import Book, Delta


class Aggregator:
    def __init__(self, manager: BookManager):
        self.manager = manager
        self.book = manager.create_book()
        self.keepers:dict[str, Keeper] = {}
        self.update_queue = manager.Queue()
        self.stop_event = manager.Event()
        self.buffers:dict[str, list[Delta]] = {}
        self.recv_seq:dict[str, int] = {}
        self.queue_processor = multiprocessing.Process(target=Aggregator.worker, args=(self.book, self.update_queue, self.stop_event))
        self.queue_processor.start()

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

    @staticmethod
    def worker(book: Book, queue: Queue, stop_event: synchronize.Event):
        while not stop_event.is_set():
            delta = queue.get()
            delta.sequence = book.sequence.value + 1
            Book.apply(book, delta)
