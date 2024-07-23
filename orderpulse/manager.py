from multiprocessing.managers import SyncManager
from sortedcontainers import SortedDict
from orderpulse.structures import Book


class BookManager(SyncManager):
    SortedDict: type[SortedDict]
    Book: type[Book]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register('SortedDict', SortedDict, exposed=('__setitem__', '__getitem__', '__delitem__', 'values', 'keys',
                                                         'items', 'popitem', 'pop', 'peekitem', 'peek', 'irange', 'get'))

    def create_book(self, bids=None, asks=None, seq=0):
        return Book(
            bids=self.SortedDict(bids or {}), 
            asks=self.SortedDict(asks or {}), 
            seq=self.Value('i', seq)
        )

