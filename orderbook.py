from datetime import datetime
from decimal import Decimal
import json
import threading
import time

from regex import R
from logger import logger
import traceback
from typing import Callable, Optional
import django

from models import Bid, OrderBook
django.setup()
from django.utils import timezone
from markets.interface import IMarket
from quantapi.models import Market, MarketSymbol


class BookKeeper:
    def __init__(self, symbol:MarketSymbol, callback:Optional[Callable]=None, market:Optional[IMarket]=None):
        self.market = market or symbol.market.get_interface()
        self.symbol = symbol
        self.orderbook = OrderBook()
        self.callbacks = [callback]
        self.name = f'{symbol.name}@{self.market.name}'
        self.thread = None

    def __str__(self):
        return f'BookKeeper ({self.name})'

    def start(self):
        if self.is_running():
            raise RuntimeError('BookKeeper is already running.')
        snapshot = self.market.get_full_orderbook(self.symbol)
        self.on_snapshot(snapshot)
        self.thread = threading.Thread(target=self.market.init_orderbook_websocket, args=(self.symbol, self.on_update))
        self.thread.start()

    def is_running(self):
        return self.thread and self.thread.is_alive()

    def format(self, data:dict):
        """convert size and price to decimal"""
        ob = OrderBook()
        ob.bids = { Decimal(bid['price']): Bid(bid['price'], bid['size']) for bid in data['bids'] }
        ob.asks = { Decimal(ask['price']): Bid(ask['price'], ask['size']) for ask in data['asks'] }
        return ob

    def on_snapshot(self, snapshot:dict):
        ob = self.format(snapshot)
        bids = {}
        asks = {}
        for bid in ob.bids.values():
            bids[bid.price] = bid
        for ask in ob.asks.values():
            asks[ask.price] = ask
        self.orderbook.bids = bids
        self.orderbook.asks = asks

    def on_update(self, update:dict):
        ob = self.format(update)
        for bid in ob.bids.values():
            bid.delta = bid.size - self.orderbook.get_bid(bid.price).size
            if bid.size <= 0:
                self.orderbook.bids.pop(bid.price, None)
            else:
                self.orderbook.bids[bid.price] = bid
        for ask in ob.asks.values():
            ask.delta = ask.size - self.orderbook.get_ask(ask.price).size
            if ask.size <= 0:
                self.orderbook.asks.pop(ask.price, None)
            else:
                self.orderbook.asks[ask.price] = ask
        for callback in self.callbacks:
            if not callable(callback):
                continue
            try:
                callback(self, ob)
            except Exception as e:
                logger.error(f'Error in callback: {e}')
                logger.error(traceback.format_exc())

    def get_best(self, limit=5):
        best_bids = sorted(self.orderbook.bids.values(), key=lambda x: x.price, reverse=True)[:limit]
        best_asks = sorted(self.orderbook.asks.values(), key=lambda x: x.price)[:limit]
        return best_bids, best_asks

    def add_callback(self, callback:Callable):
        self.callbacks.append(callback)


class BookMaster:
    def __init__(self, symbol:MarketSymbol):
        self.keepers = {}
        self.symbol = symbol
        self.orderbook = OrderBook()
        self.updates = {}
        self.callbacks = []
    
    def __str__(self):
        return f'BookMaster ({self.symbol.name})'

    def add_keeper(self, keeper:BookKeeper):
        if keeper.symbol.name != self.symbol.name:
            raise ValueError(f'Cannot add a keeper with a different symbol. Current symbol: {self.symbol}, keeper symbol: {keeper.symbol}')
        self.keepers[keeper.market] = keeper
        keeper.add_callback(self.keeper_callback)
        self.load_snapshot(keeper.orderbook)
    
    def add_callback(self, callback:Callable):
        self.callbacks.append(callback)

    def keeper_callback(self, keeper:BookKeeper, update:OrderBook):
        self.updates[keeper] = timezone.now()

        for bid in update.bids.values():
            if bid.price in self.orderbook.bids:
                self.orderbook.bids[bid.price] = self.merge_bids(self.orderbook.bids[bid.price], bid)
            else:
                self.orderbook.bids[bid.price] = bid
        
        for ask in update.asks.values():
            if ask.price in self.orderbook.asks:
                self.orderbook.asks[ask.price] = self.merge_bids(self.orderbook.asks[ask.price], ask)
            else:
                self.orderbook.asks[ask.price] = ask

        for callback in self.callbacks:
            if not callable(callback):
                continue
            try:
                callback(self, update)
            except Exception as e:
                logger.error(f'Error in callback: {e}')
                logger.error(traceback.format_exc())

    def load_snapshot(self, snapshot:OrderBook):
        # merge the snapshot with the current orderbook (self.orderbook)
        ss_bids = snapshot.bids
        ss_asks = snapshot.asks
        for bid in ss_bids.values():
            if bid.price in self.orderbook.bids:
                self.orderbook.bids[bid.price] = self.merge_bids(self.orderbook.bids[bid.price], bid)
            else:
                self.orderbook.bids[bid.price] = bid
        for ask in ss_asks.values():
            if ask.price in self.orderbook.asks:
                self.orderbook.asks[ask.price] = self.merge_bids(self.orderbook.asks[ask.price], ask)
            else:
                self.orderbook.asks[ask.price] = ask

    def merge_bids(self, bid1:Bid, bid2:Bid):
        if bid1.price != bid2.price:
            raise ValueError('Cannot merge bids with different prices')
        return Bid(bid1.price, bid1.size + bid2.size)

    def get_best(self, limit=5):
        best_bids = sorted(self.orderbook.bids.values(), key=lambda x: x.price, reverse=True)[:limit]
        best_asks = sorted(self.orderbook.asks.values(), key=lambda x: x.price)[:limit]
        return best_bids, best_asks

    def health(self):
        now = timezone.now()
        out_of_date = []
        died = []
        for keeper, last_update in self.updates.items():
            if (now - last_update).total_seconds() > 5:
                out_of_date.append(keeper)
        for keeper in self.keepers.values():
            if not keeper.is_running():
                died.append(keeper)
        return f'Out of date: {out_of_date}\nDied: {died}'


if __name__ == '__main__':
    markets = ['OKX', 'KUCOIN']
    sym = MarketSymbol.objects.filter(name='BTC-USDT').first()
    if not sym:
        raise ValueError('Symbol not found')
    master = BookMaster(sym)
    for m in markets:
        market = Market.objects.get(exchange_name=m)
        keeper = BookKeeper(sym, market=market.get_interface())
        keeper.start()
        master.add_keeper(keeper)

    lp = time.time()
    last_print = time.time()
    while True:
        if time.time() - lp < 1:
            time.sleep(0.1)
            continue
        lp = time.time()
        bids, asks = master.get_best(5)
        print(f'{datetime.now()}')
        print(f'\nBest Bids ({len(master.orderbook.bids.keys())}):')
        for bid in bids:
            print(bid)
        print(f'\nBest Asks ({len(master.orderbook.asks.keys())}):')
        for ask in asks:
            print(ask)
        print('-' * 20)
