import json
import threading
import time

from regex import R
from logger import logger
import traceback
from typing import Callable, Optional
import django
django.setup()
from django.utils import timezone
from markets.interface import IMarket
from quantapi.models import Market, MarketSymbol


class BookKeeper:
    def __init__(self, market:IMarket, symbol:MarketSymbol, callback:Optional[Callable]=None):
        self.market = market
        self.symbol = symbol
        self.orderbook = { 'bids': {}, 'asks': {} }
        self.callbacks = [callback]
        self.name = f'{symbol.name}@{market.name}'
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

    def on_snapshot(self, snapshot:dict):
        bids = {}
        asks = {}
        for bid in snapshot['bids']:
            bids[bid['price']] = bid
        for ask in snapshot['asks']:
            asks[ask['price']] = ask
        self.orderbook['bids'] = bids
        self.orderbook['asks'] = asks

    def on_update(self, update:dict):
        assert isinstance(self.orderbook, dict)
        assert isinstance(self.orderbook['bids'], dict)
        assert isinstance(self.orderbook['asks'], dict)
        assert isinstance(update, dict)
        assert 'bids' in update
        assert 'asks' in update
        bids_update = update['bids']
        asks_update = update['asks']
        for bid in bids_update:
            if bid['size'] == 0:
                self.orderbook['bids'].pop(bid['price'], None)
            else:
                self.orderbook['bids'][bid['price']] = bid
        for ask in asks_update:
            if ask['size'] == 0:
                self.orderbook['asks'].pop(ask['price'], None)
            else:
                self.orderbook['asks'][ask['price']] = ask
        for callback in self.callbacks:
            if not callable(callback):
                continue
            try:
                callback(self, update)
            except Exception as e:
                logger.error(f'Error in callback: {e}')
                logger.error(traceback.format_exc())

    def get_best(self, limit=5):
        best_bids = sorted(self.orderbook['bids'].values(), key=lambda x: x['price'], reverse=True)[:limit]
        best_asks = sorted(self.orderbook['asks'].values(), key=lambda x: x['price'])[:limit]
        return best_bids, best_asks

    def add_callback(self, callback:Callable):
        self.callbacks.append(callback)


class BookMaster:
    def __init__(self, symbol:MarketSymbol):
        self.keepers = {}
        self.symbol = symbol
        self.orderbook = { 'bids': {}, 'asks': {} }
        self.updates = {}
    
    def __str__(self):
        return f'BookMaster ({self.symbol.name})'

    def add_keeper(self, keeper:BookKeeper):
        if keeper.symbol != self.symbol:
            raise ValueError('Cannot add a keeper with a different symbol')
        self.keepers[keeper.market] = keeper
        keeper.add_callback(self.keeper_callback)
        self.load_snapshot(keeper.orderbook)

    def keeper_callback(self, keeper, update):
        self.updates[keeper] = timezone.now()
        bids_update = update['bids']
        asks_update = update['asks']
        for bid in bids_update:
            if bid['size'] == 0:
                self.orderbook['bids'].pop(bid['price'], None)
            else:
                self.orderbook['bids'][bid['price']] = bid
        for ask in asks_update:
            if ask['size'] == 0:
                self.orderbook['asks'].pop(ask['price'], None)
            else:
                self.orderbook['asks'][ask['price']] = ask

    def load_snapshot(self, snapshot:dict):
        # merge the snapshot with the current orderbook (self.orderbook)
        ss_bids = snapshot['bids']
        ss_asks = snapshot['asks']
        for bid in ss_bids.values():
            if bid['price'] in self.orderbook['bids']:
                self.orderbook['bids'][bid['price']] = self.merge_bids(self.orderbook['bids'][bid['price']], bid)
            else:
                self.orderbook['bids'][bid['price']] = bid
        for ask in ss_asks.values():
            if ask['price'] in self.orderbook['asks']:
                self.orderbook['asks'][ask['price']] = self.merge_bids(self.orderbook['asks'][ask['price']], ask)
            else:
                self.orderbook['asks'][ask['price']] = ask

    def merge_bids(self, bid1, bid2):
        if bid1['price'] != bid2['price']:
            raise ValueError('Cannot merge bids with different prices')
        return {
            'price': bid1['price'],
            'size': bid1['size'] + bid2['size'],
            'count': bid1['count'] + bid2['count']
        }

    def get_best(self, limit=5):
        best_bids = sorted(self.orderbook['bids'].values(), key=lambda x: x['price'], reverse=True)[:limit]
        best_asks = sorted(self.orderbook['asks'].values(), key=lambda x: x['price'])[:limit]
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
    markets = ['BINANCE', 'BYBIT', 'KUCOIN', 'MEXC', 'OKX', 'GATEIO']
    okx = Market.objects.get(exchange_name='MEXC').get_interface()
    gate = Market.objects.get(exchange_name='KUCOIN').get_interface()
    sym = MarketSymbol.objects.filter(name='BTC-USDT').first()
    if not sym:
        raise ValueError('Symbol not found')
    master = BookMaster(sym)
    for m in markets:
        market = Market.objects.get(exchange_name=m)
        keeper = BookKeeper(market.get_interface(), sym)
        keeper.start()
        master.add_keeper(keeper)

    last_print = time.time()
    while True:
        if time.time() - last_print > 1:
            best_bids, best_asks = master.get_best(500)
            print(f'Best Bids:')
            for bid in best_bids[:3]:
                print(f"\t{bid['price']}  {bid['size']}:{bid['count']}")
            print(f'Best Asks:')
            for ask in best_asks[:3]:
                print(f"\t{ask['price']}  {ask['size']}:{ask['count']}")
            print(master.health())
            last_print = time.time()

        time.sleep(0.1)
