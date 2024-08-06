from datetime import datetime, timedelta
from queue import Queue
from threading import Event
from orderpulse.keeper import Keeper
from orderpulse.structures import Book, Delta


class KeeperDispatch:
    def __init__(self, keeper: Keeper):
        self.interval = timedelta(seconds=1)
        self.snapshot = None
        self.delta = None
        self.buffer: Queue[Delta] = Queue()
        self.keeper = keeper
        self.synchronized = False
        self.stop_event = Event()
        self.last_sync = None
        self.callbacks = []

    def add_callback(self, callback):
        self.callbacks.append(callback)

    def synchronize(self):
        self.keeper.add_callback(self.callback)
        self.snapshot = self.keeper.snapshot()

        while not self.buffer.empty():
            delta = self.buffer.get()
            if delta.sequence > self.snapshot.sequence.value:
                Book.apply(self.snapshot, delta)
            if delta.sequence <= self.snapshot.sequence.value:
                break

        self.last_sync = datetime.now()
        self.synchronized = True

    def callback(self, delta: Delta):
        self.buffer.put(delta)

    def worker(self):
        assert self.snapshot and self.last_sync, 'KeeperDispatch must be synchronized before starting the worker'
        while not self.stop_event.is_set():
            now = datetime.now()
            if (self.last_sync - now > self.interval) and self.delta:
                self.second = now.second
                Book.apply(self.snapshot, self.delta)
                self.notify()
                self.delta = None
                self.last_sync = now
            delta = self.buffer.get()
            if delta.sequence <= self.snapshot.sequence.value:
                continue
            if not self.delta:
                self.delta = delta
            else:
                self.delta = self.delta.merge(delta)

    def notify(self):
        for callback in self.callbacks:
            callback(self.delta)
