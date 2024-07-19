from datetime import datetime
import math
import copy
from pprint import pprint
from typing import Iterable
from sortedcontainers import SortedDict


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
    def __init__(self):
        self.snapshot_applied = False
        self.bids = SortedDict()
        self.asks = SortedDict()

    def get_bids(self) -> list[Bid]:
        return list(self.bids.values())

    def get_asks(self) -> list[Bid]:
        return list(self.asks.values())

    def on_snapshot(self, snapshot: dict):
        bids = snapshot.get('bids', [])
        asks = snapshot.get('asks', [])

        for bid in bids:
            self.insert_bid(bid, 'bids')

        for ask in asks:
            self.insert_bid(ask, 'asks')

        self.snapshot_applied = True

    def copy(self):
        book = Book()
        book.bids = copy.deepcopy(self.bids)
        book.asks = copy.deepcopy(self.asks)
        return book

    def on_update(self, update: dict):
        copy = self.copy()
        bids = update.get('bids', [])
        asks = update.get('asks', [])

        for bid in bids:
            self.insert_bid(bid, 'bids')

        for ask in asks:
            self.insert_bid(ask, 'asks')
        diff = self.get_diff(copy)
        return diff

    def get_diff(self, book):
        """Get delta between self and another book (self is the newer book)"""
        diff = { 'bids': [], 'asks': [] }
        bid_px = set((*self.bids.keys(), *book.bids.keys()))
        ask_px = set((*self.asks.keys(), *book.asks.keys()))
        for px in bid_px:
            if self.bids.get(px) != book.bids.get(px):
                new_size = 0
                if self.bids.get(px):
                    new_size = self.bids[px].size
                diff['bids'].append({ 'price': px, 'size': new_size })
        for px in ask_px:
            if self.asks.get(px) != book.asks.get(px):
                new_size = 0
                if self.asks.get(px):
                    new_size = self.asks[px].size
                diff['asks'].append({ 'price': px, 'size': new_size })
        return diff

    def insert_bid(self, bid:Bid|dict, side='bids', clean=True):
        container = self.bids if side == 'bids' else self.asks
        bid = bid if isinstance(bid, Bid) else Bid(bid.get('price', 0), bid.get('size', 0))
        if bid.price and bid.size:
            container[bid.price] = bid
            if side == 'bids':
                # remove all asks with price less than this bid
                if clean:
                    new_asks = self.asks.irange(maximum=bid.price, inclusive=(False, True))
                    new_asks = list(new_asks)
                    for ask in new_asks:
                        self.asks.pop(ask, None)
            if side == 'asks':
                # remove all bids with price greater than this ask
                if clean:
                    new_bids = self.bids.irange(minimum=bid.price, inclusive=(True, False))
                    new_bids = list(new_bids)
                    for bid in new_bids:
                        self.bids.pop(bid, None)
        else:
            container.pop(bid.price, None)

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


if __name__ == '__main__':
    book = Book()
    snapshot = {
        'bids': [{'price': 100, 'size': 1}, {'price': 101, 'size': 2}, {'price': 102, 'size': 3}],
        'asks': [{'price': 103, 'size': 1}, {'price': 104, 'size': 2}, {'price': 105, 'size': 3}],
    }
    update = {
        'bids': [{'price': 100, 'size': 2}],
        'asks': [{'price': 102, 'size': 1}, {'price': 103, 'size': 3}],
    }
    book.on_snapshot(snapshot)
    diff = book.on_update(update)
    pprint(diff['bids'])
    pprint(diff['asks'])




