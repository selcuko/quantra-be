import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import pytz

from logger import logger
from markets.errors import InsufficientBalance, RejectedOrder
from models import OHLCVDataset, interval_to_minutes
from quantapi.models import ComplexOrder, Market, MarketSymbol, Order, Session, Signal
from quantapi.models import Strategy as StrategyModel
from strategy import Strategy, get_strategy


class LiveLoop:
    def __init__(self, symbol:str, market:Market, strategy:Strategy, capital_limit:float,
            asset_limit:float, freq:str='15 min', end:Optional[datetime]=None,
            session_type:Optional[str]=None, session=None, use_heikin_ashi=False) -> None:
        self.will_stop = False
        self.market = market
        self.imarket = market.get_interface()
        self.strategy = strategy
        self.strategy.freq = freq
        self.freq = freq
        self.end = end
        self.capital_limit = capital_limit
        self.asset_limit = asset_limit
        self.thread = None
        self.running = False
        self.last_kline = None
        self.use_heikin_ashi = use_heikin_ashi
        self.symbol = MarketSymbol.objects.get(name=symbol, market=market)
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
        logger.info(f'Initializing LiveLoop', extra={'loop': self})

        self.loop_interval_s = interval_to_minutes(freq) * 60
        self.last_kline_dt = None
        self.order_lock = threading.Lock()
        self.last_100_klines = None


    def __str__(self):
        return f'LL:{self.symbol.base}@{self.market.exchange_name}:{self.freq}'


    def precheck(self):
        """Prechecks before starting the live loop"""
        self.imarket.get_account()
        # validate capital and asset amound
        if self.session.capital > self.imarket.capital:
            logger.warning(f'Capital limit ({self.session.capital}) is greater than available capital ({self.imarket.capital}), updating capital limit to {self.session.capital}', extra={'loop': self})
            self.session.capital = self.imarket.capital
        if self.session.assets > self.imarket.assets.get(self.symbol.base, 0):
            logger.warning(f'Asset limit ({self.session.assets}) is greater than available assets ({self.imarket.assets.get(self.symbol.base, 0)}), updating asset limit to {self.session.assets}', extra={'loop': self})
            self.session.assets = self.imarket.assets.get(self.symbol.base, 0)
        if self.session.capital < 5 and self.session.assets <= 0:
            logger.critical(f'Capital and asset limits are too low, terminating.', extra={'loop': self})
            self.session.status = Session.Status.TERMINATED
            self.session.save()
            return False
        last_klines = self.imarket.get_last_klines(self.symbol.name, self.freq)
        if not last_klines:
            logger.critical(f'Cannot get last klines from {self.market.exchange_name}, terminating.', extra={'loop': self})
            self.session.status = Session.Status.TERMINATED
            self.session.save()
            return False
        last_klines = OHLCVDataset(last_klines)
        self.last_kline_dt = last_klines.index[-1].to_pydatetime()
        self.session.last_kline_timestamp = self.last_kline_dt
        self.last_kline = last_klines.iloc[-1].to_dict()
        self.last_100_klines = last_klines
        self.session.save()
        logger.info(f'Precheck passed, capital={self.session.capital}, assets={self.session.assets}', extra={'loop': self})
        return True


    def run(self, **kwargs):
        """Fire and forget function to start the live loop and keep it running in a seperate thread."""
        if self.running and self.thread:
            logger.error(f'LiveLoop is already running in thread {self.thread.name}, id={self.thread.ident} - refusing to start another thread.', extra={'loop': self})
            return
        self.precheck()
        self.will_stop = False
        self.running = True
        if kwargs.get('match_engine'):
            self.thread = threading.Thread(target=self.__run_match_engine, name=f'LLME:{self.symbol.base}:{self.freq.replace(" ", "")}@{self.market.exchange_name}')
        elif kwargs.get('websocket'):
            self.thread = threading.Thread(target=self.__run_websocket, name=f'LLWS:{self.symbol.base}:{self.freq.replace(" ", "")}@{self.market.exchange_name}')
            self.session.use_websocket = True
        else:
            self.thread = threading.Thread(target=self.__run_polling, name=f'LLAPI:{self.symbol.base}:{self.freq.replace(" ", "")}@{self.market.exchange_name}')
        self.thread.start()
        logger.info(f'LiveLoop started in thread {self.thread.name}, id={self.thread.ident}.', extra={'loop': self})
        self.session.started = datetime.now(tz=pytz.UTC)
        self.session.thread_id = self.thread.ident
        self.session.last_price = self.last_kline['close']
        self.session.last_kline_timestamp = self.last_kline_dt
        self.session.save()


    def stop(self):
        """Stops the live loop"""
        self.will_stop = True
        self.session.planned_shutdown = datetime.now(tz=pytz.UTC)
        logger.info(f'LiveLoop planned to shutdown after the next candle.', extra={'loop': self})


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
                    logger.warning(f'Failed to fetch last klines, retrying ({i+1}/3)', exc_info=True, extra={'loop': self})
                    time.sleep(1)
                    failed_kline_requests += 1
                    continue
            if not last_klines:
                if failed_kline_requests > MAX_FAILED_KLINE_REQUESTS:
                    logger.critical(f'Cannot get last klines, failed {failed_kline_requests} times, terminating.', extra={'loop': self})
                    break
                if not self.last_kline_dt:
                    self.last_kline_dt = datetime.now(tz=pytz.UTC)
                next_candle_time = self.last_kline_dt + timedelta(minutes=interval_to_minutes(self.freq))
                logger.error(f'Failed to fetch last klines, skipping candle ({next_candle_time})', extra={'loop': self})
                continue
            failed_kline_requests = 0
            last_klines = OHLCVDataset(last_klines)
            last_kline = {**last_klines.iloc[-1].to_dict(), 'time': last_klines.index[-1].to_pydatetime()}
            processed_ok = self.on_candle(last_kline)
            if not processed_ok:
                logger.error(f'Failed to process candle, skipping.', extra={'loop': self})
                continue
        self.running = False
        self.session.ended = datetime.now(tz=pytz.UTC)
        if self.session.status == Session.Status.ONGOING:
            self.session.status = Session.Status.COMPLETED
        self.session.save()
        self.imarket.cache_to_db()


    def __run_websocket(self):
        try:
            self.imarket.init_websocket(self.symbol.name, self.freq, self.on_candle)
        except Exception as e:
            logger.critical(f'Failed to connect to websocket, terminating.', exc_info=True, extra={'loop': self})
            self.session.status = Session.Status.ERROR
            self.session.details = repr(e)
        self.running = False
        self.session.ended = datetime.now(tz=pytz.UTC)
        self.session.status = Session.Status.COMPLETED if self.session.status == Session.Status.ONGOING else self.session.status
        self.session.save()


    def __run_match_engine(self):
        try:
            self.imarket.init_match_engine(self.symbol.name, self.freq, self.on_candle, self.session)
        except Exception as e:
            logger.critical(f'Failed to connect to match engine, terminating.', exc_info=True, extra={'loop': self})
            self.session.status = Session.Status.ERROR
            self.session.details = repr(e)
        self.running = False
        self.session.ended = datetime.now(tz=pytz.UTC)
        self.session.status = Session.Status.COMPLETED if self.session.status == Session.Status.ONGOING else self.session.status
        self.session.save()


    def on_candle(self, candle):
        if self.session.status != Session.Status.ONGOING:
            logger.error(f'Received candle while session status is {self.session.status}, skipping.', extra={'loop': self})
            return
        self.imarket.cache_to_db()
        try:
            self.last_kline_dt = candle['time']
        except KeyError:
            logger.error(f'Invalid candle received: {candle}', extra={'loop': self})
            return False
        if self.session.last_kline_timestamp and self.last_kline_dt <= self.session.last_kline_timestamp:
            return
        if self.last_100_klines is None:
            logger.error(f'Recent klines are not available, skipping candle.', extra={'loop': self})
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
        if not self.session.initial_price:
            self.session.initial_price = self.last_kline['close']
        self.session.save()

        self.run_complex_orders()


    def can_buy(self):
        """Returns whether the session can buy or not based on available capital and buy permission."""
        return self.session.capital > 5 and self.session.buy_enabled


    def can_sell(self):
        """Returns whether the session can sell or not based on available assets and sell permission."""
        return self.session.assets * (self.session.last_price or 0) > 5 and self.session.sell_enabled


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
                    last_order.market_timestamp = last_order.market_timestamp or self.last_kline_dt or datetime.now(tz=pytz.UTC)
                    last_order.save()
                    if last_order.status == Order.Status.FILLED:
                        self.session.assets += last_order.deal_size
                        self.session.capital -= last_order.deal_funds
                    else:
                        logger.error(f'{signal.side} order for {last_order.deal_funds} {self.symbol.quote} not filled, status is {last_order.status} (oid={last_order.oid}))', extra={'n_type': 'ORDER', 'loop': self})
                except InsufficientBalance:
                    self.imarket.get_account()
                    self.session.capital = max(self.imarket.capital, 0)
                    self.session.assets = max(self.imarket.assets.get(self.symbol.base, 0), 0)
                    self.session.save()
                    logger.warning(f'Insufficient balance, assets updated to {self.session.assets} and capital updated to {self.session.capital}', extra={'loop': self})
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
                        market_timestamp=self.last_kline_dt or datetime.now(tz=pytz.UTC)
                    )
                except Exception as e:
                    last_order = Order.objects.create(
                        funds=self.session.capital,
                        deal_funds=self.session.capital,
                        deal_size=self.session.capital / last_kline['close'],
                        price=last_kline['close'],
                        signal=signal,
                        status=Order.Status.ERROR,
                        details=repr(e),
                        market_timestamp=self.last_kline_dt or datetime.now(tz=pytz.UTC)
                    )
                    logger.error(f'Failed to place BUY order for {self.session.capital} {self.symbol.quote} (olid:{last_order.id}), skipping.', exc_info=True, extra={'n_type': 'ORDER', 'loop': self})
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
                    last_order.market_timestamp = last_order.market_timestamp or self.last_kline_dt or datetime.now(tz=pytz.UTC)
                    last_order.save()
                    if last_order.status == Order.Status.FILLED:
                        self.session.assets -= last_order.deal_size
                        self.session.capital += last_order.deal_funds
                    else:
                        logger.error(f'{signal.side} order for {last_order.deal_size} {self.symbol.base} not filled, status is {last_order.status} (oid={last_order.oid}))', extra={'n_type': 'ORDER', 'loop': self})
                except InsufficientBalance:
                    self.imarket.get_account()
                    self.session.capital = max(self.imarket.capital, 0)
                    self.session.assets = max(self.imarket.assets.get(self.symbol.base, 0), 0)
                    self.session.save()
                    logger.warning(f'Insufficient balance, assets updated to {self.session.assets} and capital updated to {self.session.capital}', extra={'loop': self})
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
                        market_timestamp=self.last_kline_dt or datetime.now(tz=pytz.UTC)
                    )
                except Exception as e:
                    logger.error(f'Failed to place SELL order for {self.session.assets} {self.symbol.base} (olid:{last_order.id}), skipping.', exc_info=True, extra={'n_type': 'ORDER', 'loop': self})
                    last_order = Order.objects.create(
                        funds=self.session.capital,
                        deal_funds=self.session.capital,
                        deal_size=self.session.capital / last_kline['close'],
                        price=last_kline['close'],
                        signal=signal,
                        status=Order.Status.ERROR,
                        details=repr(e),
                        market_timestamp=self.last_kline_dt or datetime.now(tz=pytz.UTC)
                    )
                self.session.save()
            else:
                return False
            return last_order


    def run_complex_orders(self):
        if self.session.status != Session.Status.ONGOING:
            return
        complex_orders = ComplexOrder.objects.filter(session=self.session, status=ComplexOrder.Status.PENDING)
        for co in complex_orders:
            if co.is_ready(self):
                co.execute(self)
                co.save()


    def should_stop(self):
        """Returns whether the loop should stop or not"""
        before_end = True
        self.session.refresh_from_db()
        if self.session.planned_shutdown:
            before_end = datetime.now(tz=pytz.UTC) < self.session.planned_shutdown
        return self.will_stop or not before_end or self.session.status != Session.Status.ONGOING


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
            logger.critical('Thread is not initialized yet.', extra={'loop': self})
            return
        while True:
            if not self.thread.is_alive():
                logger.critical(f'Thread ({self.thread.name}) died, exiting.', extra={'loop': self})
                break
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                break


if __name__ == '__main__':
    """Example usage of LiveLoop class."""
    market = Market.objects.get(exchange_name='BINANCE')
    ll = LiveLoop(
        'BNB-USDT', 
        market,
        get_strategy('v1')(
            # place optional strategy parameters here
        ),
        capital_limit=10,
        asset_limit=0,
        freq='1 min',
        use_heikin_ashi=True)
    ll.run()
    ll.idle()
