from datetime import datetime
import math
import copy
from typing import Iterable
from sortedcontainers import SortedDict

from orderpulse.manager import BookManager


class Bid:
    def __init__(self, price: float, size:float, updated:datetime|None=None):
        self.price = price
        self.size = size
        self.updated = updated or datetime.now()
        self.value = self.price * self.size

    def __hash__(self):
        return hash(self.price)

    def __repr__(self):
        return f'(price={self.price}, size={self.size})'

    def __eq__(self, other):
        if not isinstance(other, Bid):
            return False
        return self.price == other.price and self.size == other.size


class Book:
    def __init__(self, manager: BookManager):
        self.manager = manager
        self.snapshot_applied = False
        self.bids = self.manager.SortedDict()
        self.asks = self.manager.SortedDict()

    def get_bids(self) -> list[Bid]:
        return list(self.bids.values())

    def get_asks(self) -> list[Bid]:
        return list(self.asks.values())

    def on_snapshot(self, snapshot: dict):
        bids = snapshot.get('bids', [])
        asks = snapshot.get('asks', [])

        for bid in bids:
            Book.insert_bid(self.bids, self.asks, bid, 'bids')

        for ask in asks:
            Book.insert_bid(self.bids, self.asks, ask, 'asks')

        self.snapshot_applied = True

    def copy(self):
        book = Book(self.manager)
        book.bids = copy.deepcopy(self.bids)
        book.asks = copy.deepcopy(self.asks)
        return book

    @staticmethod
    def on_update(bids:SortedDict, asks:SortedDict, update: dict):
        u_bids = update.get('bids', [])
        u_asks = update.get('asks', [])
        diff = { 'bids': [], 'asks': [] }
        for bid in u_bids:
            diff.update(Book.insert_bid(bids, asks, bid, 'bids'))

        for ask in u_asks:
            diff.update(Book.insert_bid(bids, asks, ask, 'asks'))
        return diff

    @staticmethod
    def insert_bid(bids:SortedDict, asks:SortedDict, bid:Bid|dict, side='bids', clean=True):
        diff = {}
        container = bids if side == 'bids' else asks
        bid = bid if isinstance(bid, Bid) else Bid(bid.get('price', 0), bid.get('size', 0))
        if bid.price and bid.size:
            container[bid.price] = bid
            diff[bid.price] = { 'price': bid.price, 'size': bid.size }
            if side == 'bids':
                # remove all asks with price less than this bid
                if clean:
                    new_asks = asks.irange(maximum=bid.price, inclusive=(False, True))
                    new_asks = list(new_asks)
                    for ask in new_asks:
                        asks.pop(ask, None)
                        diff[ask] = { 'price': ask, 'size': 0 }
            if side == 'asks':
                # remove all bids with price greater than this ask
                if clean:
                    new_bids = bids.irange(minimum=bid.price, inclusive=(True, False))
                    new_bids = list(new_bids)
                    for bid in new_bids:
                        bids.pop(bid, None)
                        diff[bid] = { 'price': bid, 'size': 0 }
        else:
            diff[bid.price] = { 'price': bid.price, 'size': 0 }
            container.pop(bid.price, None)
        return diff

    def get_price(self):
        try:
            best_bid = self.bids.peekitem(-1)[1]
            best_ask = self.asks.peekitem(0)[1]
        except IndexError:
            return 0
        px = best_bid.price if best_bid.updated > best_ask.updated else best_ask.price
        return px

    def get_best(self, bids=None, asks=None, count=10):
        if not bids:
            bids = self.bids
        if not asks:
            asks = self.asks
        bids = list(bids.values())[-count:]
        asks = list(asks.values())[:count]
        return bids, asks

    def get_depth(self, count=10, depth:float=1):
        depthed = Depth(self.bids.values(), self.asks.values(), depth)
        bids, asks = depthed.bids, depthed.asks
        return self.get_best(bids, asks, count)


class Depth:
    def __init__(self, bids:Iterable[Bid], asks:Iterable[Bid], depth:float=1):
        self.initial_bids = copy.deepcopy(bids)
        self.initial_asks = copy.deepcopy(asks)
        self.bids = SortedDict()
        self.asks = SortedDict()
        self.depth = depth
        self.set_depth()

    def set_depth(self):
        self.set_depth_for_bids(self.initial_bids, side='bids')
        self.set_depth_for_bids(self.initial_asks, side='asks')

    def set_depth_for_bids(self, bids:Iterable[Bid], side='bids'):
        container = self.bids if side == 'bids' else self.asks
        for bid in bids:
            depthed_price = self.get_depthed_price(bid.price, side)
            if depthed_price in container:
                container[depthed_price].size += bid.size
                container[depthed_price].updated = max(container[depthed_price].updated, bid.updated)
            else:
                container[depthed_price] = Bid(depthed_price, bid.size, bid.updated)

    def get_depthed_price(self, price, side:str):
        if self.depth == 0:
            return price
        if self.depth == 1:
            if side == 'bids':
                return math.floor(price)
            return math.ceil(price)
        if self.depth > 1:
            if side == 'bids':
                return price // self.depth * self.depth
            return price // self.depth * self.depth + self.depth
        price = float(price)
        if side == 'bids':
            return math.floor(price / self.depth) * self.depth
        return math.ceil(price / self.depth) * self.depth

