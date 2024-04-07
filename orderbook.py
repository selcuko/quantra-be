import json
import threading
import time

from regex import R
from logger import logger
import traceback
from typing import Callable, Optional
import django
django.setup()
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

    def add_keeper(self, keeper:BookKeeper):
        if keeper.symbol != self.symbol:
            raise ValueError('Cannot add a keeper with a different symbol')
        self.keepers[keeper.market] = keeper
        keeper.add_callback(self.keeper_callback)
        self.load_snapshot(keeper.orderbook)

    def keeper_callback(self, keeper, update):
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


if __name__ == '__main__':
    okx = Market.objects.get(exchange_name='OKX').get_interface()
    gate = Market.objects.get(exchange_name='GATEIO').get_interface()
    sym = MarketSymbol.objects.get(name='BTC-USDT', market=okx.market)

    okx_keeper = BookKeeper(okx, sym)
    okx_keeper.start()

    gate_keeper = BookKeeper(gate, sym)
    gate_keeper.start()

    master = BookMaster(sym)
    master.add_keeper(okx_keeper)
    master.add_keeper(gate_keeper)

    last_print = time.time()
    while True:
        if time.time() - last_print > 1:
            best_bids, best_asks = master.get_best()
            print(f'Best Bids:')
            for bid in best_bids:
                print(f"\t{bid['price']}  {bid['size']}:{bid['count']}")
            print(f'Best Asks:')
            for ask in best_asks:
                print(f"\t{ask['price']}  {ask['size']}:{ask['count']}")
            last_print = time.time()
        time.sleep(0.1)
