from threading import Thread
from typing import Callable
from markets.interface import IMarket
from quantapi.models import Market, MarketSymbol


class TickerPool:
    max_pool_size = 20
    threads: dict[MarketSymbol, Thread] = {}
    callbacks: dict[MarketSymbol, list[Callable]] = {}
    interfaces: dict[Market, IMarket] = {}

    @classmethod
    def add_callback(cls, symbol: MarketSymbol, callback: Callable):
        if symbol not in cls.callbacks:
            cls.callbacks[symbol] = []
        cls.callbacks[symbol].append(callback)

    @classmethod
    def remove_callback(cls, symbol: MarketSymbol, callback: Callable):
        if symbol not in cls.callbacks or callback not in cls.callbacks[symbol]:
            return
        cls.callbacks[symbol].remove(callback)
        if not cls.callbacks[symbol]:
            del cls.callbacks[symbol]
        if not cls.callbacks:
            print('no more callbacks, stopping ticker...')
            cls.stop(symbol)

    @classmethod
    def get(cls, symbol: MarketSymbol, callback: Callable) -> Thread:
        cls.add_callback(symbol, callback)
        if symbol in cls.threads:
            if cls.threads[symbol].is_alive():
                print('symbol already in pool')
                return cls.threads[symbol]
            print('symbol found in pool but thread is not alive, restarting...')
            cls.stop(symbol)
            cls.add_callback(symbol, callback)
        cls.start(symbol)
        return cls.threads[symbol]

    @classmethod
    def start(cls, symbol: MarketSymbol):
        if not symbol.market in cls.interfaces:
            print('market interface not found, initializing...')
            cls.interfaces[symbol.market] = symbol.market.get_interface()
        print('starting ticker thread...')
        thread = Thread(
            target=cls.interfaces[symbol.market].init_match_engine, 
            args=(symbol.name, '1 min', cls.callback, None, None, cls.callback)
        )
        thread.start()
        cls.threads[symbol] = thread
        return thread

    @classmethod
    def stop(cls, symbol: MarketSymbol):
        if symbol not in cls.threads:
            return
        cls.interfaces[symbol.market].stop_websocket_stream = True
        thread = cls.threads[symbol]
        thread.join()
        del cls.threads[symbol]
        try:
            del cls.callbacks[symbol]
        except KeyError:
            pass
        print('ticker thread stopped')

    @classmethod
    def make_callback(cls, symbol: MarketSymbol):
        def callback(candle: dict):
            for callbacks in cls.callbacks.values():
                for callback in callbacks:
                    callback(candle)
        return callback

    @classmethod
    def cleanup(cls, symbol: MarketSymbol):
        cls.stop(symbol)
        try:
            del cls.interfaces[symbol.market]
        except KeyError:
            pass
        print('ticker pool cleaned up')