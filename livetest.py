import json
import django
django.setup()
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Optional

import pytz

from logger import logger
from markets import IMarket
from markets.errors import InsufficientBalance, MarketAPIError, RejectedOrder
from models import OHLCVDataset, interval_to_minutes
from quantapi.models import (Market, Order, Session, Signal,
                             Symbol, Strategy as StrategyModel)
from strategy import Strategy, get_strategy
from testman import TestManager


class LiveLoop:
    def __init__(self, symbol:str, market:Market, strategy:Strategy, capital_limit:float,
            asset_limit:float, freq:str='15 min', end:Optional[datetime]=None,
            session_type:Optional[str]=None, session=None) -> None:
        self.will_stop = False
        self.market = market
        self.imarket = market.get_interface()
        self.strategy = strategy
        self.freq = freq
        self.end = end
        self.capital_limit = capital_limit
        self.asset_limit = asset_limit
        self.thread = None
        self.running = False
        logger.info(f'Initializing live loop for {symbol} on {market.exchange_name}')

        self.symbol = Symbol.objects.get_or_create(name=symbol, market=market)[0]
        if not (strategy_model := StrategyModel.objects.filter(name=strategy.name).first()):
            strategy_model = StrategyModel.objects.create(name=strategy.name, parameters=json.dumps(strategy.params))
        strategy_model.parameters = json.dumps(strategy.params)
        strategy_model.save()
        self.session = session or Session.objects.create(
            symbol=self.symbol,
            session_type=session_type,
            freq=freq,
            strategy=strategy_model,
            planned_shutdown=end,
            status=Session.Status.ONGOING,
            capital=capital_limit,
            assets=asset_limit,
            initial_capital=capital_limit,
            initial_assets=asset_limit,
        )

        self.loop_interval_s = interval_to_minutes(freq) * 60
        self.last_kline_dt = None
        self.order_lock = threading.Lock()

    def precheck(self):
        """Prechecks before starting the live loop"""
        self.imarket.get_account()
        # validate capital and asset amound
        if self.session.capital > self.imarket.capital:
            raise InsufficientBalance(f'Capital limit ({self.session.capital}) is greater than available capital ({self.imarket.capital})')
        if self.session.assets > self.imarket.assets.get(self.symbol.base, 0):
            raise InsufficientBalance(f'Asset limit ({self.session.assets}) is greater than available assets ({self.imarket.assets.get(self.symbol.base, 0)})')

    def run(self):
        """Fire and forget function to start the live loop and keep it running in a seperate thread."""
        if self.running and self.thread:
            raise RuntimeError(f'Live loop is already running in thread {self.thread.name}, id={self.thread.ident}')
        self.precheck()
        self.will_stop = False
        self.running = True
        self.thread = threading.Thread(target=self.__run, name=f'LL:{self.symbol.base}:{self.freq.replace(" ", "")}@{self.market.exchange_name}')
        self.thread.start()
        self.session.started = datetime.now(tz=pytz.UTC)
        self.session.thread_id = self.thread.ident
        self.session.save()

    def stop(self):
        """Stops the live loop"""
        self.will_stop = True
        self.session.planned_shutdown = datetime.now(tz=pytz.UTC)

    def __run(self):
        logger.info(f'Starting live loop for {self.symbol} on {self.imarket.name} with freq {self.freq.replace(" ", "").upper()}')
        last_klines = []
        failed_kline_requests = 0
        while not self.should_stop() and self.wait_next_candle() and not self.should_stop():
            got_klines = False
            for i in range(3):
                if got_klines:
                    break
                try:
                    last_klines = self.imarket.get_last_klines(self.symbol.name, self.freq)
                    got_klines = True
                    break
                except:
                    logger.warning(f'Failed to fetch last klines, retrying ({i+1}/3)', exc_info=True)
                    time.sleep(1)
                    failed_kline_requests += 1
                    continue
            if not last_klines:
                if failed_kline_requests > 9:
                    logger.error(f'Cannot get last klines, failed {failed_kline_requests} times, exiting')
                    break
                logger.error(f'Failed to fetch last klines, skipping')
                continue
            failed_kline_requests = 0
            raw_dataset = OHLCVDataset(last_klines)
            strategy_dataset = self.strategy(raw_dataset)

            self.last_kline_dt = strategy_dataset.index[-1].to_pydatetime()
            if self.session.last_kline_timestamp and self.last_kline_dt <= self.session.last_kline_timestamp:
                continue
            last_kline = {'time': self.last_kline_dt.timestamp(), **strategy_dataset.iloc[-1].to_dict()}
            positive_buy_signal = last_kline['buy']
            positive_sell_signal = last_kline['sell']

            if positive_buy_signal:
                self.__buy(last_kline)
            
            elif positive_sell_signal:
                self.__sell(last_kline)
            
            self.session.last_kline_timestamp = self.last_kline_dt
            self.session.save()

        self.running = False
        self.session.ended = datetime.now(tz=pytz.UTC)
        self.session.status = Session.Status.COMPLETED
        self.session.save()

    def can_buy(self):
        return self.session.capital > 0
    
    def can_sell(self):
        return self.session.assets > 0

    def __buy(self, last_kline:dict):
        with self.order_lock:
            last_order = None
            signal = Signal.objects.create(
                session=self.session,
                timestamp=self.last_kline_dt,
                side=Signal.Side.BUY,
                price=last_kline['close'],
                raw=last_kline)
            if self.can_buy():
                try:
                    last_order = self.imarket.place_market_order(self.symbol.name, 'buy', funds=self.session.capital)
                    last_order.signal = signal
                    last_order.price = last_kline['close']
                    last_order.save()
                    if last_order.status == Order.Status.FILLED:
                        self.session.assets += last_order.deal_size
                        self.session.capital -= last_order.deal_funds
                    else:
                        logger.warning(f'Order not filled, status is {last_order.status}')
                except InsufficientBalance:
                    self.imarket.get_account()
                    self.session.capital = self.imarket.capital
                    self.session.assets = self.imarket.assets[self.symbol.base]
                    self.session.save()
                    logger.warning(f'Insufficient balance, assets updated to {self.session.assets} and capital updated to {self.session.capital}')
                    return self.__buy(last_kline)
                except RejectedOrder as ro:
                    last_order = Order.objects.create(
                        funds=self.session.capital,
                        deal_funds=self.session.capital,
                        deal_size=self.session.capital / last_kline['close'],
                        price=last_kline['close'],
                        signal=signal,
                        status=Order.Status.REJECTED,
                        market_response=repr(ro),
                        timestamp=self.last_kline_dt
                    )
                except:
                    logger.error('Failed to place market order, skipping', exc_info=True)
                    return
                self.session.save()
            else:
                return False
            return last_order

    def __sell(self, last_kline:dict):
        with self.order_lock:
            if not last_kline:
                last_kline = {}
            last_order = None
            signal = None
            signal = Signal.objects.create(
                session=self.session,
                timestamp=self.last_kline_dt,
                side=Signal.Side.SELL,
                price=last_kline['close'],
                raw=last_kline)
            if self.can_sell():
                try:
                    last_order = self.imarket.place_market_order(self.symbol.name, 'sell', quantity=self.session.assets)
                    last_order.signal = signal
                    last_order.price = last_kline['close']
                    last_order.save()
                    if last_order.status == Order.Status.FILLED:
                        self.session.assets -= last_order.deal_size
                        self.session.capital += last_order.deal_funds
                    else:
                        logger.warning(f'Order not filled, status is {last_order.status}')
                except InsufficientBalance:
                    self.imarket.get_account()
                    self.session.capital = self.imarket.capital
                    self.session.assets = self.imarket.assets[self.symbol.base]
                    self.session.save()
                    logger.warning(f'Insufficient balance, assets updated to {self.session.assets} and capital updated to {self.session.capital}')
                    return self.__sell(last_kline)
                except RejectedOrder as ro:
                    last_order = Order.objects.create(
                        funds=self.session.capital,
                        deal_funds=self.session.capital,
                        deal_size=self.session.assets,
                        price=last_kline['close'],
                        signal=signal,
                        status=Order.Status.REJECTED,
                        market_response=repr(ro),
                        timestamp=self.last_kline_dt
                    )
                except:
                    logger.error('Failed to place market order, skipping', exc_info=True)
                    return
                self.session.save()
            else:
                return False
            return last_order

    def should_stop(self):
        """Returns whether the loop should stop or not"""
        before_end = True
        self.session.refresh_from_db()
        if self.session.planned_shutdown:
            before_end = datetime.now(tz=pytz.UTC) < self.session.planned_shutdown
        return self.will_stop or not before_end

    def wait_next_candle(self):
        """Waits until the next candle should be available"""
        if not self.last_kline_dt:
            return True
        last_kline_ts = self.last_kline_dt.timestamp()
        residue = last_kline_ts + self.loop_interval_s + 5 - time.time()
        if residue > 0:
            slept = 0
            while residue > 0 and not self.will_stop:
                time.sleep(1)
                slept += 1
                residue -= 1
        else:
            time.sleep(1)
        return True

    def idle(self):
        """Idle indefinitely (for development purposes)"""
        if not self.thread:
            logger.warning('Thread is not initialized yet.')
            return
        while True:
            if not self.thread.is_alive():
                logger.error(f'Thread ({self.thread.name}) died, exiting')
                break
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                break


def run_livetest(symbol:str, market:IMarket, strategy:Callable, freq='15 min', end:Optional[datetime]=None):
    _symbol = Symbol.objects.get_or_create(name=symbol, market=market.name)[0]
    session = Session.objects.create(
        symbol=_symbol,
        session_type=Session.Type.LIVE_BASIC,
        freq=freq,
        planned_shutdown=end,
        status=Session.Status.ONGOING,
    )
    testman = TestManager(
        symbol=_symbol.name, 
        market=market, 
        type='live.basic', 
        strategy=strategy,
        capital=100,
        assets=100,
        interval=freq)
    if isinstance(end, timedelta):
        end = datetime.now(tz=pytz.UTC) + end

    logger.info(f'Running live test on {symbol} from {market.name} with freq {freq.replace(" ", "").upper()}, planned shutdown at {end}')

    def break_check():
        # more like brake check haha
        if end and datetime.now(tz=pytz.UTC) > end:
            return True
        return False

    loop_interval = interval_to_minutes(freq) * 60

    while True:
        if break_check():
            break
        try:
            klines = market.get_last_klines(symbol, freq)
        except MarketAPIError:
            logger.fatal(f'Fatal error halted program while fetching klines for {symbol} from {market.name}')
            testman.shutdown()
            return
        ds = OHLCVDataset(klines)
        ds = strategy(ds)
        should_buy = ds.iloc[-1]['buy']
        should_sell = ds.iloc[-1]['sell']
        kline = {'time': ds.index[-1].timestamp(), **ds.iloc[-1].to_dict()}
        if should_buy:
            signal = Signal.objects.create(
                session=session,
                timestamp=ds.index[-1],
                side=Signal.Side.BUY,
                price=kline['close'],
                raw=kline)
            if not testman.bought:
                testman.buy(kline)
                last_order = testman.trades[-1]
                Order.objects.create(
                    deal_funds=last_order.capital,
                    price=last_order.price,
                    quantity=last_order.assets,
                    signal=signal
                )    
        elif should_sell:
            signal = Signal.objects.create(
                session=session,
                timestamp=ds.index[-1],
                side=Signal.Side.SELL,
                price=kline['close'],
                raw=kline)
            if not testman.bought:
                testman.sell(kline)
                last_order = testman.trades[-1]
                Order.objects.create(
                    deal_size=last_order.capital,
                    price=last_order.price,
                    deal_funds=last_order.assets,
                    funds=last_order.capital,
                    signal=signal
                )
        print(testman.summary())
        try:
            time.sleep(loop_interval)
        except KeyboardInterrupt:
            logger.info('KeyboardInterrupt detected, shutting down gracefully')
            break
    testman.shutdown()


if __name__ == '__main__':
    

    """market = Market.objects.get(testnet_enabled=True, exchange_name='BINANCE')
    ll = LiveLoop(
        'BTC-USDT', 
        market,
        get_strategy('v1')(),
        capital_limit=100,
        asset_limit=0.1,
        freq='1 min')
    ll.run()
    #ll.idle() """
    """    s = Session.objects.get(pk=37)
    s.resume()
    while True:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            #ll.stop()
            break"""
    pass
