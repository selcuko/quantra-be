from datetime import datetime
import math
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


class Book:
    def __init__(self):
        self.snapshot_applied = False
        self.bids: SortedDict = SortedDict()
        self.asks = SortedDict()

    def on_snapshot(self, snapshot: dict):
        bids = snapshot.get('bids', [])
        asks = snapshot.get('asks', [])

        for bid in bids:
            self.insert_bid(bid, 'bids')

        for ask in asks:
            self.insert_bid(ask, 'asks')

        self.snapshot_applied = True

    def on_update(self, update: dict):
        bids = update.get('bids', [])
        asks = update.get('asks', [])

        for bid in bids:
            self.insert_bid(bid, 'bids')

        for ask in asks:
            self.insert_bid(ask, 'asks')

    def insert_bid(self, bid:dict, side='bids'):
        container = self.bids if side == 'bids' else self.asks
        price, size = bid.get('price', 0), bid.get('size', 0)
        if price and size:
            container[price] = Bid(price, size)
            if side == 'bids':
                # remove all asks with price less than this bid
                new_asks = self.asks.irange(maximum=price, inclusive=(False, True))
                new_asks = list(new_asks)
                for ask in new_asks:
                    self.asks.pop(ask, None)
            if side == 'asks':
                # remove all bids with price greater than this ask
                new_bids = self.bids.irange(minimum=price, inclusive=(True, False))
                new_bids = list(new_bids)
                for bid in new_bids:
                    self.bids.pop(bid, None)
        else:
            container.pop(price, None)

    def get_price(self):
        best_bid = self.bids.peekitem(-1)[1]
        best_ask = self.asks.peekitem(0)[1]
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
    def __init__(self, bids:list, asks:list, depth:float=1):
        self.initial_bids = bids
        self.initial_asks = asks
        self.bids = SortedDict()
        self.asks = SortedDict()
        self.depth = depth
        self.set_depth()

    def set_depth(self):
        self.set_depth_for_bids(self.initial_bids, side='bids')
        self.set_depth_for_bids(self.initial_asks, side='asks')

    def set_depth_for_bids(self, bids:list, side='bids'):
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
        'bids': [{'price': 100.5, 'size': 1}, {'price': 100.66, 'size': 2}, {'price': 100.1293, 'size': 3}],
        'asks': [{'price': 100.7484, 'size': 1}, {'price': 101.123, 'size': 2}, {'price': 100.99, 'size': 3}],
    }
    update = {
        'bids': [{'price': 98, 'size': 2}, {'price': 99, 'size': 0}],
        'asks': [{'price': 101, 'size': 0}, {'price': 102, 'size': 3}],
    }
    book.on_snapshot(snapshot)
    depth = Depth(book.bids.values(), book.asks.values(), depth=0.1)
    print(depth.bids)
    print(depth.asks)




