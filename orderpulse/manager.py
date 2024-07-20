from multiprocessing.managers import SyncManager
from sortedcontainers import SortedDict

class BookManager(SyncManager):
    SortedDict: type[SortedDict]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register('SortedDict', SortedDict, exposed=('__setitem__', '__getitem__', '__delitem__', 'values', 'keys',
                                                         'items', 'popitem', 'pop', 'peekitem', 'peek', 'irange', 'get'))

