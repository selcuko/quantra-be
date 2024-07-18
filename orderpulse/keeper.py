import threading
from typing import Callable, Optional
from orderpulse.structures import Book
from markets.interface import IMarket
from quantapi.models import MarketSymbol, MarketAccount


class KeeperPool:
    pool: dict['MarketSymbol', 'BookKeeper'] = {}

    @classmethod
    def get(cls, symbol:'MarketSymbol', callback:Optional[Callable]=None):
        if (keeper := cls.pool.get(symbol)):
            if callback and callback not in keeper.callbacks:
                keeper.add_callback(callback)
            return keeper
        account = MarketAccount.objects.filter(market=symbol.market).first()
        if not account:
            raise RuntimeError('No account found for market')
        keeper = BookKeeper(symbol, account, callback)
        cls.pool[symbol] = keeper
        return keeper


class BookKeeper:
    def __init__(self, symbol:'MarketSymbol', account:'MarketAccount', callback:Optional[Callable]=None, interface:Optional['IMarket']=None):
        self.interface = interface or account.get_interface()
        self.account = account
        self.symbol = symbol
        self.callbacks = [callback] if callback else []
        self.name = f'BookKeeper of {symbol.name}@{self.interface.name}'
        self.thread = None
        self.book = Book()

    def __str__(self):
        return self.name

    def start(self):
        if self.is_running():
            raise RuntimeError('You called start() on a BookKeeper that is already running.')
        snapshot = self.interface.get_full_orderbook(self.symbol)
        self.on_snapshot(snapshot)
        self.thread = threading.Thread(target=self.interface.init_orderbook_websocket, args=(self.symbol, self.on_update), daemon=True)
        self.thread.start()

    def is_running(self):
        return self.thread and self.thread.is_alive()

    def on_snapshot(self, snapshot:dict):
        self.book.on_snapshot(snapshot)

    def on_update(self, update:dict):
        self.book.on_update(update)
        for callback in self.callbacks:
            callback(update)

    def add_callback(self, callback:Callable):
        self.callbacks.append(callback)

    def stop(self):
        if self.thread and self.thread.is_alive():
            self.interface.stop_websocket_stream = True
            self.thread.join()


