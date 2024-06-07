import django
django.setup()
from django.core.cache import cache
from order import OrderManager
import json
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import pytz

from logger import logger
from markets.errors import OrderPostProcessingError
from models import OHLCVDataset, interval_to_minutes
from quantapi.models import Market, MarketAccount, MarketSymbol, Order, Session, Signal, ComplexOrder
from quantapi.models import Strategy as StrategyModel
from strategy import Strategy, get_strategy

class LiveLoop:
    def __init__(self, symbol:str, account:MarketAccount, strategy:Strategy, capital_limit:float,
                 asset_limit:float, freq:str='15 min', end:Optional[datetime]=None,
                 session_type:Optional[str]=None, session:Session|None=None, use_heikin_ashi=False) -> None:

        self.account = account
        self.market = self.account.market
        self.imarket = self.account.get_interface()
        self.strategy = strategy
        self.strategy.freq = freq
        self.freq = freq
        self.end = end
        self.capital_limit = capital_limit
        self.asset_limit = asset_limit
        self.use_heikin_ashi = use_heikin_ashi
        self.symbol = MarketSymbol.objects.get(name=symbol, market=self.market)

        self.thread = None
        self.running = False
        self.last_kline = None
        self.will_stop = False
        self.last_kline_dt = None
        self.last_100_klines = None

        self.loop_interval_s = interval_to_minutes(freq) * 60

        if not (strategy_model := StrategyModel.objects.filter(name=strategy.name).first()):
            strategy_model = StrategyModel.objects.create(name=strategy.name)

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
            strategy_parameters=json.dumps(strategy.params),
            account=self.account,
        )
        cache.set(f'session_{self.session.pk}', self, timeout=None)

        logger.info(f'LiveLoop initialized.', extra={'loop': repr(self)})

    def __str__(self):
        return f'LL:{self.symbol.base}@{self.market.exchange_name}:{self.freq}'
    
    def __repr__(self):
        return f'{self.symbol.base}@{self.market.exchange_name}:{self.freq}'

    def precheck(self):
        """Prechecks before starting the live loop"""
        self.imarket.get_account()
        # validate capital and asset amound
        market_capital = self.imarket.capital
        market_assets = self.imarket.assets.get(self.symbol.base, 0)
        if self.session.capital > self.imarket.capital:
            logger.warning(f'Capital limit ({self.session.capital}) is greater than available capital ({market_capital}), updating capital limit to {market_capital}', extra={'loop': repr(self)})
            self.session.capital = self.imarket.capital
        if self.session.assets > self.imarket.assets.get(self.symbol.base, 0):
            logger.warning(f'Asset limit ({self.session.assets}) is greater than available assets ({market_assets}), updating asset limit to {market_assets}', extra={'loop': repr(self)})
            self.session.assets = self.imarket.assets.get(self.symbol.base, 0)
        if self.session.capital < 5 and self.session.assets <= 0:
            logger.critical(f'Capital and asset limits are too low, terminating ({self.session.capital} {self.symbol.quote}, {self.session.assets} {self.symbol.base}).', extra={'loop': repr(self)})
            self.session.status = Session.Status.TERMINATED
            self.session.save()
            return False
        return True

    def prepare_kline_snapshot(self):
        """Prepares the last kline and last 100 klines for the session."""
        last_klines = self.imarket.get_last_klines(self.symbol.name, self.freq)
        if not last_klines:
            logger.critical(f'Cannot get last klines from {self.market.exchange_name}, terminating.', extra={'loop': repr(self)})
            self.session.status = Session.Status.TERMINATED
            self.session.save()
            return False

        last_klines = OHLCVDataset(last_klines)
        self.last_kline_dt = last_klines.index[-1].to_pydatetime()
        self.session.last_kline_timestamp = self.last_kline_dt
        self.last_kline = last_klines.iloc[-1].to_dict()
        self.last_100_klines = last_klines
        self.session.save()
        return True

    def run(self, **kwargs):
        """Fire and forget function to start the live loop and keep it running in a seperate thread."""
        if self.running and self.thread:
            logger.error(f'LiveLoop is already running in thread {self.thread.name}, id={self.thread.ident} - refusing to start another thread.', extra={'loop': repr(self)})
            return
        precheck_ok = self.precheck()
        if not precheck_ok:
            logger.error(f'Precheck failed, terminating.', extra={'loop': repr(self)})
            return
        snapshot_ok = self.prepare_kline_snapshot()
        if not snapshot_ok:
            logger.error(f'Failed to prepare kline snapshot, terminating.', extra={'loop': repr(self)})
            return
        self.will_stop = False
        self.running = True
        if kwargs.get('match_engine'):
            self.thread = threading.Thread(target=self.__run_match_engine, name=f'LLME:{self.symbol.base}:{self.freq.replace(" ", "")}@{self.market.exchange_name}')
            self.session.candle_source = Session.CandleSource.TRADE
        elif kwargs.get('websocket'):
            self.thread = threading.Thread(target=self.__run_websocket, name=f'LLWS:{self.symbol.base}:{self.freq.replace(" ", "")}@{self.market.exchange_name}')
            self.session.candle_source = Session.CandleSource.WEBSOCKET
        else:
            self.thread = threading.Thread(target=self.__run_polling, name=f'LLAPI:{self.symbol.base}:{self.freq.replace(" ", "")}@{self.market.exchange_name}')
            self.session.candle_source = Session.CandleSource.REST
        self.thread.start()
        logger.info(f'LiveLoop started in thread {self.thread.name}, id={self.thread.ident}.', extra={'loop': repr(self)})
        self.session.started = datetime.now(tz=pytz.UTC)
        self.session.thread_id = self.thread.ident
        self.session.last_price = self.last_kline['close'] if self.last_kline else None
        self.session.last_kline_timestamp = self.last_kline_dt
        self.session.save()


    def stop(self):
        """Stops the live loop"""
        self.will_stop = True
        self.session.planned_shutdown = datetime.now(tz=pytz.UTC)
        logger.info(f'LiveLoop planned to shutdown after the next candle.', extra={'loop': repr(self)})

    def run_ticker_until_next_candle(self):
        """Runs the ticker until the next candle should be available"""
        if not self.last_kline_dt:
            return
        last_kline_ts = self.last_kline_dt.timestamp()
        now_ts = time.time()
        residue = last_kline_ts + self.loop_interval_s - now_ts
        if residue > 0:
            slept = 0
            while residue > 0 and not self.will_stop:
                time.sleep(1)
                slept += 1
                residue -= 1
                print(f'\rSleeping for {residue}s ({slept}s)', end='', flush=True)
        else:
            print('neg res', residue)
            time.sleep(1)
        return True

    def __run_polling(self):
        MAX_FAILED_KLINE_REQUESTS = 10
        last_klines = []
        failed_kline_requests = 0
        while True:
            self.run_ticker_until_next_candle()
            for i in range(3):
                try:
                    last_klines = self.imarket.get_last_klines(self.symbol.name, self.freq)
                    break
                except:
                    logger.warning(f'Failed to fetch last klines, retrying ({i+1}/3)', exc_info=True, extra={'loop': repr(self)})
                    time.sleep(1)
                    failed_kline_requests += 1
                    continue
            if not last_klines:
                if failed_kline_requests > MAX_FAILED_KLINE_REQUESTS:
                    logger.critical(f'Cannot get last klines, failed {failed_kline_requests} times, terminating.', extra={'loop': repr(self)})
                    break
                if not self.last_kline_dt:
                    self.last_kline_dt = datetime.now(tz=pytz.UTC)
                next_candle_time = self.last_kline_dt + timedelta(minutes=interval_to_minutes(self.freq))
                logger.error(f'Failed to fetch last klines, skipping candle ({next_candle_time})', extra={'loop': repr(self)})
                continue
            failed_kline_requests = 0
            last_klines = OHLCVDataset(last_klines)
            last_kline = {**last_klines.iloc[-1].to_dict(), 'time': last_klines.index[-1].to_pydatetime()}
            processed_ok = self.on_candle(last_kline)
            if processed_ok is False:
                logger.error(f'Failed to process candle, skipping.', extra={'loop': repr(self)})
                continue
        self.running = False
        self.session.ended = datetime.now(tz=pytz.UTC)
        if self.session.status == Session.Status.ONGOING:
            self.session.status = Session.Status.COMPLETED
        self.session.save()
        self.imarket.cache_to_db()


    def __run_websocket(self):
        try:
            self.imarket.init_websocket(self.symbol.name, self.freq, self.on_candle, self)
        except Exception as e:
            logger.critical(f'Failed to connect to websocket, terminating.', exc_info=True, extra={'loop': repr(self)})
            self.session.status = Session.Status.ERROR
            self.session.details = repr(e)
        self.running = False
        self.session.ended = datetime.now(tz=pytz.UTC)
        self.session.status = Session.Status.COMPLETED if self.session.status == Session.Status.ONGOING else self.session.status
        self.session.save()


    def __run_match_engine(self):
        try:
            self.imarket.init_match_engine(self.symbol.name, self.freq, self.on_candle, self)
        except Exception as e:
            logger.critical(f'Failed to connect to match engine, terminating.', exc_info=True, extra={'loop': repr(self)})
            self.session.status = Session.Status.ERROR
            self.session.details = repr(e)
        self.running = False
        self.session.ended = datetime.now(tz=pytz.UTC)
        self.session.status = Session.Status.COMPLETED if self.session.status == Session.Status.ONGOING else self.session.status
        self.session.save()


    def on_candle(self, candle):
        if self.session.status != Session.Status.ONGOING:
            logger.warning(f'Received candle while session status is {self.session.status}, skipping.', extra={'loop': repr(self)})
            return
        equity = self.session.capital + self.session.assets * (self.session.last_price or 999999999)
        if equity < 5:
            logger.error(f'Ghost session found - no capital ({self.session.capital}) and no assets ({self.session.assets}) ({equity=}), pausing. [SessionID:{self.session.pk}]', extra={'loop': repr(self)})
            self.session.status = Session.Status.PAUSED
            self.session.save()
        self.imarket.cache_to_db()
        try:
            self.last_kline_dt = candle['time']
        except KeyError:
            logger.error(f'Invalid candle received: {candle}', extra={'loop': repr(self)})
            return False
        if self.session.last_kline_timestamp and self.last_kline_dt <= self.session.last_kline_timestamp:
            logger.warning(f'Old kline received, skipping (received={self.last_kline_dt}, processed={self.session.last_kline_timestamp}).', extra={'loop': repr(self)})
            return
        if self.last_100_klines is None:
            logger.error(f'Recent klines are not available, skipping candle.', extra={'loop': repr(self)})
        candle = OHLCVDataset([candle])
        self.last_100_klines = pd.concat([self.last_100_klines, candle])
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
        return True


    def can_buy(self):
        """Returns whether the session can buy or not based on available capital and buy permission."""
        return self.session.capital >= 5 and self.session.buy_enabled


    def can_sell(self):
        """Returns whether the session can sell or not based on available assets and sell permission."""
        return self.session.assets * (self.session.last_price or 0) >= 5 and self.session.sell_enabled


    def buy(self, last_kline:dict):
        """Buys the asset if possible. Returns the order object if successful, None otherwise. Meant to be called from on_candle method."""
        signal = Signal.objects.create(
            session=self.session,
            timestamp=self.last_kline_dt,
            side=Signal.Side.BUY,
            price=float(last_kline['close']),
            raw=last_kline)
        if not self.can_buy():
            return
        order_manager = OrderManager(self.imarket, self.session)

        try:
            order = order_manager.place(
                symbol=self.symbol,
                side='buy',
                deal_funds=self.session.capital,
            )
        except OrderPostProcessingError as e:
            logger.error(f'Order post processing failed. Order might or might no be placed. {e!r}', extra={'type': 'ORDER', 'prefix': repr(self)})
        except:
            logger.error(f'Unhandled error while placing order.', exc_info=True, extra={'type': 'ORDER', 'loop': repr(self)})
            return

        if order.status == Order.Status.INSUFFICIENT_BALANCE:
            self.imarket.get_account()
            old_cap = self.session.capital
            self.session.capital = max(self.imarket.capital, 0)
            self.session.save()
            logger.warning(f'Insufficient balance, capital updated to {self.session.capital}', extra={'prefix': repr(self), 'type': 'ORDER'})
            if old_cap == self.session.capital:
                return
            return self.buy(last_kline)
        elif order.status == Order.Status.REJECTED:
            logger.error(f'RejectedOrder: {order!s}', extra={'type': 'ORDER', 'prefix': repr(self)})
        elif order.status == Order.Status.FILLED and order.deal_size and order.deal_funds:
            self.session.assets += order.deal_size
            self.session.capital -= order.deal_funds
            self.session.save()
        order.signal = signal
        order.save()
        return order


    def sell(self, last_kline:dict):
        """Sells the asset if possible. Returns the order object if successful, None otherwise. Meant to be called from on_candle method."""
        signal = Signal.objects.create(
            session=self.session,
            timestamp=self.last_kline_dt,
            side=Signal.Side.SELL,
            price=float(last_kline['close']),
            raw=last_kline)
        if not self.can_sell():
            return
        order_manager = OrderManager(self.imarket, self.session)

        try:
            order = order_manager.place(
                symbol=self.symbol,
                side='sell',
                deal_size=self.session.assets,
            )
        except OrderPostProcessingError as e:
            logger.error(f'Order post processing failed. Order might or might no be placed. {e!r}', extra={'type': 'ORDER', 'prefix': repr(self)})
        except:
            logger.error(f'Unhandled error while placing order.', exc_info=True, extra={'type': 'ORDER', 'loop': repr(self)})
            return

        if order.status == Order.Status.INSUFFICIENT_BALANCE:
            self.imarket.get_account()
            old_assets = self.session.assets
            self.session.assets = self.imarket.assets.get(self.symbol.base, 0)
            self.session.save()
            logger.warning(f'Insufficient balance, assets updated to {self.session.assets}', extra={'prefix': repr(self), 'type': 'ORDER'})
            if old_assets == self.session.assets:
                return
            return self.sell(last_kline)
        elif order.status == Order.Status.REJECTED:
            logger.error(f'RejectedOrder: {order!s}', extra={'type': 'ORDER', 'prefix': repr(self)})
        elif order.status == Order.Status.FILLED and order.deal_size and order.deal_funds:
            self.session.assets -= order.deal_size
            self.session.capital += order.deal_funds
            self.session.save()
        order.signal = signal
        order.save()
        return order


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
        if self.will_stop:
            return True
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
                print(f'\rSleeping for {residue}s ({slept}s)', end='', flush=True)
        else:
            print('neg res', residue)
            time.sleep(1)
        return True


    def idle(self):
        """Idle indefinitely (for development purposes)"""
        if not self.thread:
            logger.critical('Thread is not initialized yet.', extra={'loop': repr(self)})
            return
        while True:
            if not self.thread.is_alive():
                logger.critical(f'Thread ({self.thread.name}) died, exiting.', extra={'loop': repr(self)})
                break
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                break


if __name__ == '__main__':
    """Example usage of LiveLoop class."""
    market = MarketAccount.objects.get(market__exchange_name='MEXC')
    if not market:
        raise Exception('No market account found.')
    ll = LiveLoop(
        'BNB-USDT', 
        market,
        get_strategy('bb')(
            # place optional strategy parameters here
        ),
        capital_limit=10,
        asset_limit=0,
        freq='1 min')
    ll.run()
    started = datetime.now()
    while datetime.now() - started < timedelta(minutes=10):
        time.sleep(1)
        print('.', end='', flush=True)
