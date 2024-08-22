from contextlib import contextmanager
from orderpulse.manager import BookManager


class ReadWriteLock:
    """An extended version of multiprocessing.Lock that allows multiple readers or a single writer to acquire the lock."""
    def __init__(self, manager: BookManager):
        self.__read_ready = manager.Condition(manager.Lock())
        self.__readers = manager.Value('i', 0)

    @contextmanager
    def read(self):
        self.acquire_read()
        try:
            yield
        finally:
            self.release_read()

    @contextmanager
    def write(self):
        self.acquire_write()
        try:
            yield
        finally:
            self.release_write()

    def acquire_read(self):
        with self.__read_ready:
            self.__readers.value += 1

    def release_read(self):
        with self.__read_ready:
            self.__readers.value -= 1
            if not self.__readers.value:
                self.__read_ready.notify_all()

    def acquire_write(self):
        with self.__read_ready:
            while self.__readers.value:
                self.__read_ready.wait()

    def release_write(self):
        with self.__read_ready:
            self.__read_ready.notify_all()
