import json
import django
import pandas as pd
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
from django.utils import timezone
from websockets.sync.client import connect


class LiveLoop:
    def __init__(self, symbol:str, market:Market, strategy:Strategy, capital_limit:float,
            asset_limit:float, freq:str='15 min', end:Optional[datetime]=None,
            session_type:Optional[str]=None, session=None, use_heikin_ashi=False) -> None:
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
        self.last_kline = None
        self.use_heikin_ashi = use_heikin_ashi
        logger.info(f'Initializing live loop for {symbol} on {market.exchange_name}')

        self.symbol = Symbol.objects.get(name=symbol, market=market)
        if not (strategy_model := StrategyModel.objects.filter(name=strategy.name).first()):
            strategy_model = StrategyModel.objects.create(name=strategy.name, parameters=json.dumps(strategy.params))
        strategy_model.save()
        self.session = session or Session.objects.create(
            symbol=self.symbol,
            session_type=session_type or Session.Type.LIVE_MAINNET,
            freq=freq,
            strategy=strategy_model,
            planned_shutdown=end,
            status=Session.Status.ONGOING,
            capital=capital_limit,
            assets=asset_limit,
            initial_capital=capital_limit,
            initial_assets=asset_limit,
            strategy_parameters=json.dumps(strategy.params)
        )

        self.loop_interval_s = interval_to_minutes(freq) * 60
        self.last_kline_dt = None
        self.order_lock = threading.Lock()
        self.last_100_klines = None

    def precheck(self):
        """Prechecks before starting the live loop"""
        self.imarket.get_account()
        # validate capital and asset amound
        if self.session.capital > self.imarket.capital:
            logger.warning(f'Capital limit ({self.session.capital}) is greater than available capital ({self.imarket.capital}), updating capital limit to {self.session.capital}')
            self.session.capital = self.imarket.capital
        if self.session.assets > self.imarket.assets.get(self.symbol.base, 0):
            logger.warning(f'Asset limit ({self.session.assets}) is greater than available assets ({self.imarket.assets.get(self.symbol.base, 0)}), updating asset limit to {self.session.assets}')
            self.session.assets = self.imarket.assets.get(self.symbol.base, 0)
        last_klines = self.imarket.get_last_klines(self.symbol.name, self.freq)
        if not last_klines:
            logger.error(f'Cannot get last klines from {self.market.exchange_name}, exiting')
            raise RuntimeError(f'Cannot get last klines from {self.market.exchange_name}, exiting')
        last_klines = OHLCVDataset(last_klines)
        self.last_kline_dt = last_klines.index[-1].to_pydatetime()
        self.session.last_kline_timestamp = self.last_kline_dt
        self.last_kline = last_klines.iloc[-1].to_dict()
        self.last_100_klines = last_klines
        self.session.save()

    def run(self, **kwargs):
        """Fire and forget function to start the live loop and keep it running in a seperate thread."""
        if self.running and self.thread:
            raise RuntimeError(f'Live loop is already running in thread {self.thread.name}, id={self.thread.ident}')
        if kwargs.get('polling') == kwargs.get('websocket') == True:
            raise RuntimeError('You must choose either polling or websocket')
        self.precheck()
        self.will_stop = False
        self.running = True
        if kwargs.get('websocket'):
            self.thread = threading.Thread(target=self.__run_websocket, name=f'LL:{self.symbol.base}:{self.freq.replace(" ", "")}@{self.market.exchange_name}')
            self.session.use_websocket = True
        else:
            self.thread = threading.Thread(target=self.__run_polling, name=f'LL:{self.symbol.base}:{self.freq.replace(" ", "")}@{self.market.exchange_name}')
        self.thread.start()
        self.session.started = datetime.now(tz=pytz.UTC)
        self.session.thread_id = self.thread.ident
        self.session.save()

    def stop(self):
        """Stops the live loop"""
        self.will_stop = True
        self.session.planned_shutdown = datetime.now(tz=pytz.UTC)

    def __run_polling(self):
        MAX_FAILED_KLINE_REQUESTS = 10
        last_klines = []
        failed_kline_requests = 0
        while not self.should_stop() and self.wait_next_candle() and not self.should_stop():
            for i in range(3):
                try:
                    last_klines = self.imarket.get_last_klines(self.symbol.name, self.freq)
                    break
                except:
                    logger.warning(f'Failed to fetch last klines from {self.market.exchange_name}, retrying ({i+1}/3)', exc_info=True)
                    time.sleep(1)
                    failed_kline_requests += 1
                    continue
            if not last_klines:
                if failed_kline_requests > MAX_FAILED_KLINE_REQUESTS:
                    logger.error(f'Cannot get last klines, failed {failed_kline_requests} times for {self.market.exchange_name}, exiting')
                    break
                if not self.last_kline_dt:
                    self.last_kline_dt = datetime.now(tz=pytz.UTC)
                next_candle_time = self.last_kline_dt + timedelta(minutes=interval_to_minutes(self.freq))
                logger.error(f'Failed to fetch last klines from {self.market.exchange_name}, skipping this candle ({next_candle_time})')
                continue
            failed_kline_requests = 0
            last_klines = OHLCVDataset(last_klines)
            last_kline = {**last_klines.iloc[-1].to_dict(), 'time': last_klines.index[-1].to_pydatetime()}
            processed_ok = self.on_candle(last_kline)

    def __run_websocket(self):
        ws_uri = self.imarket.get_websocket_uri(self.symbol.name, self.freq)
        try:
            ws = connect(ws_uri)
            while True:
                if self.should_stop():
                    break
                payload_str = ws.recv()
                payload = json.loads(payload_str)
                candle = self.imarket.format_ws_candle(payload)
                if candle['last']:
                    self.on_candle(candle)
        except Exception as e:
            logger.error(f'Failed to connect to websocket {ws_uri}, exiting', exc_info=True)
            return

    def on_candle(self, candle):
        try:
            self.last_kline_dt = candle['time']
        except KeyError:
            logger.error(f'Invalid candle received: {candle}')
            return False
        if self.session.last_kline_timestamp and self.last_kline_dt <= self.session.last_kline_timestamp:
            return
        if self.last_100_klines is None:
            raise RuntimeError('last_100_klines is not initialized')
        self.last_100_klines = (pd.concat([self.last_100_klines, OHLCVDataset([candle])]))
        self.last_100_klines = self.last_100_klines.iloc[-100:]
        raw_dataset = OHLCVDataset(self.last_100_klines, pass_thru=True)
        if self.use_heikin_ashi:
            raw_dataset = raw_dataset.convert_to_heikin_ashi()
        strategy_dataset = self.strategy(raw_dataset)

        self.last_kline_dt = strategy_dataset.index[-1].to_pydatetime()
        
        self.last_kline = {'time': self.last_kline_dt.timestamp(), **strategy_dataset.iloc[-1].to_dict()}
        positive_buy_signal = self.last_kline['buy']
        positive_sell_signal = self.last_kline['sell']

        if positive_buy_signal:
            self.buy(self.last_kline)
        
        elif positive_sell_signal:
            self.sell(self.last_kline)
        
        self.session.last_kline_timestamp = self.last_kline_dt
        self.session.last_price = self.last_kline['close']
        self.session.save()

        self.running = False
        self.session.ended = datetime.now(tz=pytz.UTC)
        self.session.status = Session.Status.COMPLETED
        self.session.save()

    def can_buy(self):
        return self.session.capital > 5
    
    def can_sell(self):
        return self.session.assets * (self.session.last_price or 0) > 5

    def buy(self, last_kline:dict):
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
                    last_order.timestamp = last_order.timestamp or self.last_kline_dt or datetime.now(tz=pytz.UTC)
                    last_order.save()
                    if last_order.status == Order.Status.FILLED:
                        self.session.assets += last_order.deal_size
                        self.session.capital -= last_order.deal_funds
                    else:
                        logger.warning(f'Order not filled, status is {last_order.status} (oid={last_order.oid}))')
                except InsufficientBalance:
                    self.imarket.get_account()
                    self.session.capital = self.imarket.capital
                    self.session.assets = self.imarket.assets.get(self.symbol.base, 0)
                    self.session.save()
                    logger.warning(f'Insufficient balance, assets updated to {self.session.assets} and capital updated to {self.session.capital}')
                    return self.buy(last_kline)
                except RejectedOrder as ro:
                    last_order = Order.objects.create(
                        funds=self.session.capital,
                        deal_funds=self.session.capital,
                        deal_size=self.session.capital / last_kline['close'],
                        price=last_kline['close'],
                        signal=signal,
                        status=Order.Status.REJECTED,
                        details=repr(ro),
                        timestamp=self.last_kline_dt or datetime.now(tz=pytz.UTC)
                    )
                except Exception as e:
                    logger.error(f'Failed to place market buy order for {self.session.capital} {self.symbol.quote}, skipping', exc_info=True)
                    last_order = Order.objects.create(
                        funds=self.session.capital,
                        deal_funds=self.session.capital,
                        deal_size=self.session.capital / last_kline['close'],
                        price=last_kline['close'],
                        signal=signal,
                        status=Order.Status.ERROR,
                        details=repr(e),
                        timestamp=self.last_kline_dt or datetime.now(tz=pytz.UTC)
                    )
                self.session.save()
            else:
                return False
            return last_order

    def sell(self, last_kline:dict):
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
                    last_order.timestamp = last_order.timestamp or self.last_kline_dt or datetime.now(tz=pytz.UTC)
                    last_order.save()
                    if last_order.status == Order.Status.FILLED:
                        self.session.assets -= last_order.deal_size
                        self.session.capital += last_order.deal_funds
                    else:
                        logger.warning(f'Order not filled, status is {last_order.status}, oid={last_order.oid}')
                except InsufficientBalance:
                    self.imarket.get_account()
                    self.session.capital = self.imarket.capital
                    self.session.assets = self.imarket.assets.get(self.symbol.base, 0)
                    self.session.save()
                    logger.warning(f'Insufficient balance, assets updated to {self.session.assets} and capital updated to {self.session.capital}')
                    return self.sell(last_kline)
                except RejectedOrder as ro:
                    last_order = Order.objects.create(
                        funds=self.session.capital,
                        deal_funds=self.session.capital,
                        deal_size=self.session.assets,
                        price=last_kline['close'],
                        signal=signal,
                        status=Order.Status.REJECTED,
                        details=repr(ro),
                        timestamp=self.last_kline_dt or datetime.now(tz=pytz.UTC)
                    )
                except Exception as e:
                    logger.error(f'Failed to place market sell order for {self.session.assets} {self.symbol.base}, skipping', exc_info=True)
                    last_order = Order.objects.create(
                        funds=self.session.capital,
                        deal_funds=self.session.capital,
                        deal_size=self.session.capital / last_kline['close'],
                        price=last_kline['close'],
                        signal=signal,
                        status=Order.Status.ERROR,
                        details=repr(e),
                        timestamp=self.last_kline_dt or datetime.now(tz=pytz.UTC)
                    )
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
        return self.will_stop or not before_end and self.session.status != Session.Status.ONGOING

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
    

    market = Market.objects.get(exchange_name='BINANCE')
    ll = LiveLoop(
        'BNB-USDT', 
        market,
        get_strategy('v1')(),
        capital_limit=10,
        asset_limit=0,
        freq='1 min',
        use_heikin_ashi=True)
    ll.run()
    ll.idle()
    while True:
        try:
            td = timezone.now() - ll.session.started
            #print('Time elapsed:', td)
            """if td > timedelta(seconds=5):
                last_kline = ll.last_kline
                ll.buy(last_kline)
                exit()"""
            time.sleep(1)
        except KeyboardInterrupt:
            ll.stop()
            break
