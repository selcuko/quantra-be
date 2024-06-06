from re import A
import threading
import time
import traceback
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable, Optional


from logger import logger
from models import Bid, OrderBook

from django.utils import timezone
import typing
if typing.TYPE_CHECKING:
    from markets.interface import IMarket
    from quantapi.models import Market, MarketSymbol



class BookKeeper:
    def __init__(self, symbol:'MarketSymbol', callback:Optional[Callable]=None, market:Optional['IMarket']=None):
        self.market = market or symbol.market.get_interface()
        self.symbol = symbol
        self.orderbook = OrderBook()
        self.callbacks = [callback] if callback else []
        self.name = f'BookKeeper of {symbol.name}@{self.market.name}'
        self.thread = None

    def __str__(self):
        return self.name

    def start(self):
        """Start the BookKeeper in the background, in another thread."""
        if self.is_running():
            raise RuntimeError('This BookKeeper is already running.')
        snapshot = self.market.get_full_orderbook(self.symbol)
        self.on_snapshot(snapshot)
        self.thread = threading.Thread(target=self.market.init_orderbook_websocket, args=(self.symbol, self.on_update), daemon=True)
        self.thread.start()

    def is_running(self):
        return self.thread and self.thread.is_alive()

    def format(self, data:dict):
        """Converts size and price to decimal"""
        ob = OrderBook()
        ob.bids = { Decimal(bid['price']): Bid(bid['price'], bid['size']) for bid in data['bids'] }
        ob.asks = { Decimal(ask['price']): Bid(ask['price'], ask['size']) for ask in data['asks'] }
        return ob

    def on_snapshot(self, snapshot:dict):
        """Called when a snapshot is received. Populates the orderbook with the snapshot."""
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
        """Called when an update is received. Updates the orderbook with the update."""
        ob_update = self.format(update)
        for bid in ob_update.bids.values():
            bid.delta = bid.size - self.orderbook.get_bid(bid.price).size
            if bid.size <= 0:
                self.orderbook.bids.pop(bid.price, None)
            else:
                self.orderbook.bids[bid.price] = bid
        for ask in ob_update.asks.values():
            ask.delta = ask.size - self.orderbook.get_ask(ask.price).size
            if ask.size <= 0:
                self.orderbook.asks.pop(ask.price, None)
            else:
                self.orderbook.asks[ask.price] = ask
        for callback in self.callbacks:
            if not callable(callback):
                continue
            try:
                callback(self, ob_update)
            except Exception as e:
                logger.error(f'Error in callback: {e}')
                logger.error(traceback.format_exc())

    def add_callback(self, callback:Callable):
        """Add a callback to be called when an update is received."""
        self.callbacks.append(callback)

    def stop(self):
        if self.thread and self.thread.is_alive():
            self.market.stop_websocket_stream = True
            self.thread.join()


class BookMaster:
    def __init__(self, symbol:'MarketSymbol'):
        self.keepers:dict[IMarket, BookKeeper] = {}
        self.symbol = symbol
        self.orderbook = OrderBook()
        self.updates = {}
        self.callbacks = []
        self.name = f'BookMaster of {symbol.name}'
    
    def __str__(self):
        return self.name

    def add_keeper(self, keeper:BookKeeper):
        if keeper.symbol.name != self.symbol.name:
            raise ValueError(f'Cannot add a BookKeeper with a different symbol. Current symbol is {self.symbol.name}, what you were trying to add is: {keeper.symbol.name}')
        self.keepers[keeper.market] = keeper
        keeper.add_callback(self.keeper_callback)
        self.load_snapshot(keeper.orderbook)
    
    def add_callback(self, callback:Callable):
        self.callbacks.append(callback)

    def keeper_callback(self, keeper:BookKeeper, update:OrderBook):
        """Called when any BookKeeper receives an update. Updates the BookMaster's orderbook with the update."""
        self.updates[keeper] = timezone.now()

        for bid in update.bids.values():
            px = bid.price
            total_sz = sum([ k.orderbook.bids[px].size for k in self.keepers.values() if px in k.orderbook.bids ])
            if total_sz > 0:
                self.orderbook.bids[px] = Bid(px, total_sz)
            else:
                self.orderbook.bids.pop(px, None)

        for ask in update.asks.values():
            px = ask.price
            total_sz = sum([ k.orderbook.asks[px].size for k in self.keepers.values() if px in k.orderbook.asks ])
            if total_sz > 0:
                self.orderbook.asks[px] = Bid(px, total_sz)
            else:
                self.orderbook.asks.pop(px, None)

        for callback in self.callbacks:
            if not callable(callback):
                continue
            try:
                callback(self, update)
            except Exception as e:
                logger.error(f'Error in callback: {e}')
                logger.error(traceback.format_exc())

    def load_snapshot(self, snapshot:OrderBook):
        # Merge the snapshot with the current orderbook (self.orderbook)
        ss_bids = snapshot.bids
        ss_asks = snapshot.asks
        for bid in ss_bids.values():
            if bid.price in self.orderbook.bids:
                print('IN')
                self.orderbook.bids[bid.price] = self.merge_bids(self.orderbook.bids[bid.price], bid)
            else:
                print('OUT')
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

    def stop(self):
        for keeper in self.keepers.values():
            keeper.stop()


if __name__ == '__main__':
    # note to self: for program not exiting on it's own problem, ensure that the websocket thread is terminated OK (it's not daemon)
    import django
    django.setup()
    from markets.interface import IMarket
    from quantapi.models import Market, MarketSymbol
    
    bybit = Market.objects.get(exchange_name='BYBIT')
    btc_bybit = MarketSymbol.objects.get(name='BTC-USDT', market=bybit)

    okx = Market.objects.get(exchange_name='MEXC')
    btc_okx = MarketSymbol.objects.get(name='BTC-USDT', market=okx)

    bybit_keeper = BookKeeper(btc_bybit)
    okx_keeper = BookKeeper(btc_okx)

    master = BookMaster(btc_bybit)
    master.add_keeper(bybit_keeper)
    master.add_keeper(okx_keeper)

    bybit_keeper.start()
    okx_keeper.start()
    
    while True:
        try:
            print(master.orderbook.format())
            print(master.orderbook.overview())
            print(master.health())
            time.sleep(1)
        except KeyboardInterrupt:
            break
