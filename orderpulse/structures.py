import copy
from datetime import datetime
from decimal import Decimal
import json
import math
from multiprocessing.managers import ValueProxy
from typing import Any, Iterable, Optional

from sortedcontainers import SortedDict


class Bid:
    def __init__(self, price: Decimal, size: Decimal, updated: Optional[datetime]=None):
        assert price >= 0,                  'price must be greater than 0: %s' % price
        assert isinstance(price, Decimal),  'price must be a Decimal'
        assert isinstance(size, Decimal),   'size must be a Decimal'
        self.price = price
        self.size = size
        self.value = price * size
        self.updated = updated or datetime.now()

    def __repr__(self):
        return f'Bid(price={self.price}, size={self.size})'

    def __eq__(self, other):
        if not isinstance(other, Bid):
            return False
        return self.price == other.price and self.size == other.size

    def dict(self):
        return {
            'price': str(self.price),
            'size': str(self.size),
        }

    def json(self):
        return json.dumps(self.dict())


class Delta:
    def __init__(self, sequence: int|None, received: datetime, processed: datetime|None, bids: dict[Decimal, Bid]|None=None, asks: dict[Decimal, Bid]|None=None, market:str=''):
        self.sequence = sequence or -1
        self.received = received
        self.processed = processed
        self.bids = bids or SortedDict()
        self.asks = asks or SortedDict()
        self.market = market

    def __repr__(self):
        return f'Delta(sequence={self.sequence}, received={self.received}, processed={self.processed}, bids={len(self.bids.keys())}, asks={len(self.asks.keys())})'

    def merge(self, other):
        """Merges this Delta with another Delta. The other Delta is assumed to be the newer one."""
        processed = max(self.processed, other.processed) if self.processed and other.processed else self.processed or other.processed
        self.sequence=max(self.sequence, other.sequence)
        self.received=max(self.received, other.received)
        self.processed=processed
        self.bids.update(other.bids)
        self.asks.update(other.asks)

    def dict(self):
        return {
            'type': 'delta',
            'sequence': self.sequence,
            'received': self.received.isoformat(),
            'processed': self.processed.isoformat() if self.processed else None,
            'bids': [ (str(bid.price), str(bid.size)) for bid in self.bids.values() ],
            'asks': [ (str(ask.price), str(ask.size)) for ask in self.asks.values() ],
        }

    def json(self):
        return json.dumps(self.dict())


class Book:
    def __init__(self, bids:SortedDict, asks:SortedDict, seq:ValueProxy[int]):
        self.bids = bids
        self.asks = asks
        self.sequence = seq

    def __repr__(self):
        return f'Book(bids={len(self.bids.keys())}, asks={len(self.asks.keys())}, seq={self.sequence.value})'

    @staticmethod
    def convert(payload:dict[str, Any]):
        """Converts the market payload to a Delta object"""
        return Delta(
            sequence=payload.get('sequence'),
            received=payload['received'],
            processed=payload.get('processed'),
            bids=SortedDict({Decimal(bid['price']): Bid(Decimal(bid['price']), Decimal(bid['size'])) for bid in payload['bids']}),
            asks=SortedDict({Decimal(ask['price']): Bid(Decimal(ask['price']), Decimal(ask['size'])) for ask in payload['asks']}),
            market=payload['market'],
        )

    @staticmethod
    def apply(book: 'Book', delta: Delta, verify_sequence=True):
        """Applies a Delta to a Book (as a difference delta)"""
        if verify_sequence:
            assert book.sequence.value < delta.sequence, f'Delta sequence {delta.sequence} must be greater than the Book sequence {book.sequence.value}'
        book.sequence.value = delta.sequence
        for price, bid in delta.bids.items():
            if old_bid := book.bids.get(price):
                book.bids[price] = Bid(price, old_bid.size + bid.size)
            else:
                book.bids[price] = Bid(price, bid.size)
            if book.bids[price].size == 0:
                del book.bids[price]
        for price, ask in delta.asks.items():
            if old_ask := book.asks.get(price):
                book.asks[price] = Bid(price, old_ask.size + ask.size)
            else:
                book.asks[price] = Bid(price, ask.size)
            if book.asks[price].size == 0:
                del book.asks[price]

    @staticmethod
    def insert(book: 'Book', delta: Delta) -> Delta:
        """Inserts a Delta into a Book (as a new state), and returns a Delta with the difference"""
        assert book.sequence.value < delta.sequence, f'Delta sequence {delta.sequence} must be greater than the Book sequence {book.sequence.value}'
        book.sequence.value = delta.sequence
        diff_delta = Delta(
            sequence=delta.sequence,
            received=delta.received,
            processed=None,
            bids=SortedDict(),
            asks=SortedDict(),
            market=delta.market,
        )
        for bid in delta.bids.values():
            if bid.size:
                old_size = 0
                if old_bid := book.bids.get(bid.price):
                    old_size = old_bid.size
                book.bids[bid.price] = bid
                if bid.size - old_size:
                    diff_delta.bids[bid.price] = Bid(bid.price, bid.size - old_size)
                outdated_asks = book.asks.irange(maximum=bid.price, inclusive=(False, True))
                outdated_asks = list(outdated_asks)
                for outdated_ask in outdated_asks:
                    dropped_ask = book.asks.pop(outdated_ask, None)
                    if isinstance(dropped_ask, Bid) and dropped_ask.size:
                        diff_delta.asks[outdated_ask] = Bid(outdated_ask, -dropped_ask.size)
            elif isinstance(dropped_bid := book.bids.pop(bid.price, None), Bid):
                diff_delta.bids[bid.price] = Bid(bid.price, -dropped_bid.size)

        for ask in delta.asks.values():
            if ask.size:
                old_size = 0
                if old_ask := book.asks.get(ask.price):
                    old_size = old_ask.size
                book.asks[ask.price] = ask
                if ask.size - old_size:
                    diff_delta.asks[ask.price] = Bid(ask.price, ask.size - old_size)
                outdated_bids = book.bids.irange(minimum=ask.price, inclusive=(True, False))
                outdated_bids = list(outdated_bids)
                for outdated_bid in outdated_bids:
                    dropped_bid = book.bids.pop(outdated_bid, None)
                    if isinstance(dropped_bid, Bid) and dropped_bid.size:
                        diff_delta.bids[outdated_bid] = Bid(outdated_bid, -dropped_bid.size)
            elif isinstance(dropped_ask := book.asks.pop(ask.price, None), Bid):
                diff_delta.asks[ask.price] = Bid(ask.price, -dropped_ask.size)
        return diff_delta

    @staticmethod
    def merge(main: 'Book', snapshot: 'Book'):
        """Merges a snapshot into the main book. Values in snapshot are interpreted as deltas"""
        delta = Delta(
            sequence=main.sequence.value + 1,
            received=datetime.now(),
            processed=None,
            bids=copy.deepcopy(snapshot.bids),
            asks=copy.deepcopy(snapshot.asks),
        )
        Book.apply(main, delta)
        return delta

    def get_price(self) -> Decimal:
        try:
            best_bid = self.bids.peekitem(-1)[1]
            best_ask = self.asks.peekitem(0)[1]
        except IndexError:
            return Decimal(0)
        return best_bid.price if best_bid.updated > best_ask.updated else best_ask.price

    def get_best(self, bids:Optional[Iterable[Bid]]=None, asks:Optional[Iterable[Bid]]=None, count=5, range_asks=0, range_bids=0):
        """Returns the best bids and asks"""
        if not bids:
            bids = self.bids.values()
        if not asks:
            asks = self.asks.values()
        if range_asks or range_bids:
            return (
                list(bids)[-range_bids:],
                list(asks)[:range_asks]
            )
        else:
            return (
                list(bids)[-count:],
                list(asks)[:count],
            )

    def get_depth(self, count=5, depth=Decimal(1), range_asks=0, range_bids=0):
        depth = Depth(self, depth)
        return self.get_best(bids=depth.bids.values(), asks=depth.asks.values(), count=count, range_asks=range_asks, range_bids=range_bids)

    def dict(self):
        return {
            'type': 'book',
            'sequence': self.sequence.value,
            'bids': [ (str(bid.price), str(bid.size)) for bid in self.bids.values()],
            'asks': [ (str(ask.price), str(ask.size)) for ask in self.asks.values()],
        }

    def json(self):
        return json.dumps(self.dict())


class Depth:
    def __init__(self, book: Book, depth:Decimal=Decimal(1)):
        self.book = book
        self.bids = SortedDict()
        self.asks = SortedDict()
        self.depth = Decimal(depth)
        self.set_depth()

    def set_depth(self):
        self.set_depth_for_bids(self.book.bids.values(), side='bids')
        self.set_depth_for_bids(self.book.asks.values(), side='asks')

    def set_depth_for_bids(self, bids:Iterable[Bid], side='bids'):
        container = self.bids if side == 'bids' else self.asks
        for bid in bids:
            depthed_price = self.get_depth_price(bid.price, side)
            if depthed_price in container:
                container[depthed_price].size += bid.size
                container[depthed_price].updated = max(container[depthed_price].updated, bid.updated)
            else:
                container[depthed_price] = Bid(depthed_price, bid.size, bid.updated)

    def get_depth_price(self, price:Decimal, side:str):
        if self.depth == 0:
            return price
        if self.depth == 1:
            if side == 'bids':
                return Decimal(math.floor(price))
            return Decimal(math.ceil(price))
        if self.depth > 1:
            if side == 'bids':
                return Decimal(price // self.depth * self.depth)
            return Decimal(price // self.depth * self.depth + self.depth)
        if side == 'bids':
            return Decimal(math.floor(price / self.depth) * self.depth)
        return Decimal(math.ceil(price / self.depth) * self.depth)
