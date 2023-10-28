import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Optional

import pytz

from logger import logger
from markets import IMarket, MarketError, get_market
from models import OHLCVDataset, interval_to_minutes
from quantapi.models import (Market, Order, Session, Signal, Subscription,
                             Symbol, User)
from strategy import Strategy, get_strategy
from testman import TestManager


class LiveLoop:
    def __init__(
            self,
            symbol:str,
            market:IMarket,
            strategy:Strategy,
            capital_limit:float,
            asset_limit:float,
            initiating_user:Optional[User]=None,
            freq:str='15 min',
            end:Optional[datetime]=None,
            session=None,
            market_id_for_symbol:Optional[int]=None,
        ) -> None:
        self.will_stop = False
        self.market = market
        self.strategy = strategy
        self.freq = freq
        self.end = end
        self.capital_limit = capital_limit
        self.asset_limit = asset_limit
        self.thread = None
        self.running = False
        
        if market_id_for_symbol:
            self.symbol = Symbol.objects.get_or_create(name=symbol, market_id=market_id_for_symbol)[0]
        else:
            self.symbol = Symbol.objects.get_or_create(name=symbol, market__exchange_name=market.name)[0]
        self.session = session or Session.objects.create(
            symbol=self.symbol,
            session_type=Session.Type.LIVE_SANDBOX,
            freq=freq,
            strategy_name=strategy.name,
            strategy_parameters=strategy.params,
            planned_shutdown=end,
            status=Session.Status.ONGOING,
            capital=capital_limit,
            assets=asset_limit,
            initial_capital=capital_limit,
            initial_assets=asset_limit,
        )
        self.user = initiating_user
        if self.user:
            Subscription.objects.create(user=self.user, session=self.session)
        else:
            logger.warning('No user provided, notification system disabled')

        self.testman = TestManager(
            symbol=symbol,
            market=self.market,
            type='live.sandbox',
            strategy=strategy,
            interval=freq,
            capital=capital_limit,
            assets=asset_limit,
            commission=self.market.commission
        )
        self.loop_interval_s = interval_to_minutes(freq) * 60
        self.last_kline_dt = None
        self.session.notify('Initiating live test - hope the core is stable 🤞')
        # signal.signal(signal.SIGINT, self.handle_sigint)
        

    def run(self):
        """Fire and forget function to start the live loop and keep it running in a seperate thread."""
        if self.running:
            raise RuntimeError('Already running')
        self.will_stop = False
        self.running = True
        self.thread = threading.Thread(target=self.__run, name=f'LL:{self.symbol.base}@{self.market.name}')
        self.thread.start()

    def __run(self):
        logger.info(f'Starting live loop for {self.symbol} on {self.market.name} with freq {self.freq.replace(" ", "").upper()}')
        summary = None
        while not self.should_stop() and self.wait_next_candle() and not self.should_stop():
            # self.handle_manual_overrides()

            last_klines = self.market.get_last_klines(self.symbol.name, self.freq)
            raw_dataset = OHLCVDataset(last_klines)
            strategy_dataset = self.strategy(raw_dataset)

            self.last_kline_dt = strategy_dataset.index[-1].to_pydatetime()
            last_kline = {'time': self.last_kline_dt.timestamp(), **strategy_dataset.iloc[-1].to_dict()}
            positive_buy_signal = last_kline['buy']
            positive_sell_signal = last_kline['sell']

            self.testman.update(last_kline)

            if positive_buy_signal:
                self.__buy()
            
            elif positive_sell_signal:
                self.__sell()

            summary = self.testman.summary()
            logger.info(summary)

        self.running = False
        report = self.testman.shutdown(save=True)
        self.session.ended = datetime.now(tz=pytz.UTC)
        self.session.report = report
        self.session.status = Session.Status.COMPLETED
        self.session.save()
        self.session.notify_complete(f'Live loop completed, summary: {summary}')
    
    def __buy(self, last_kline={}, force=False):
        last_order = None
        if not force:
            signal = Signal.objects.create(
                session=self.session,
                timestamp=self.last_kline_dt,
                side=Signal.Side.BUY,
                price=last_kline.get('close', -1),
                raw=last_kline)
            self.session.notify_signal(signal)
        else:
            signal = Signal.objects.create(
                session=self.session,
                timestamp=datetime.utcnow(),
                side=Signal.Side.BUY,
                price=-1,
                raw='FORCED')
        if self.testman.can_buy() or force:
            try:
                last_order = self.market.place_market_order(self.symbol.name, 'buy', funds=self.testman.capital)
            except:
                logger.error('Failed to place market order, skipping', exc_info=True)
                return
            last_order.signal = signal
            last_order.save()
            self.session.notify_order(last_order)
        self.testman.buy(last_kline, sync=last_order)
        return last_order

    def __sell(self, last_kline=None, force=False):
        if not last_kline:
            last_kline = {}
        last_order = None
        signal = None
        if not force:
            signal = Signal.objects.create(
                session=self.session,
                timestamp=self.last_kline_dt,
                side=Signal.Side.SELL,
                price=last_kline.get('close', -1),
                raw=last_kline)
            self.session.notify_signal(signal)
        if self.testman.can_sell() or force:
            last_order = self.market.place_market_order(self.symbol.name, 'sell', quantity=self.testman.assets)
            if signal:
                last_order.signal = signal
            last_order.save()
            self.session.notify_order(last_order)
        self.testman.sell(last_kline, sync=last_order)
        return last_order

    def handle_manual_overrides(self):
        """Handle manual overrides such as force buy, update capital limit etc."""
        raise NotImplementedError

    def should_stop(self):
        """Returns whether the loop should stop or not

        Returns:
            bool: True if the loop should stop, False otherwise
        """
        before_end = True
        if self.end:
            before_end = datetime.now(tz=pytz.UTC) < self.end
        return self.will_stop or not before_end

    def wait_next_candle(self):
        """Waits until the next candle is available"""
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
            # new candle is not available yet
            time.sleep(1)
        return True

    def stop(self, set_completed=True):
        self.will_stop = True
        if set_completed:
            self.session.status = Session.Status.COMPLETED
            self.session.save()
    
    def force_buy(self):
        if self.testman.bought:
            logger.error('Already bought, skipping')
            return
        return self.__buy(force=True)

    def force_sell(self):
        raise NotImplementedError

    def force_shutdown(self):
        raise NotImplementedError

    def update_capital_limit(self):
        raise NotImplementedError

    def update_asset_limit(self):
        raise NotImplementedError

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

    def handle_sigint(self, sig, frame):
        logger.info('SIGINT detected, shutting down gracefully')
        self.stop(False)
        logger.info('Shutdown complete')


def run_livetest(symbol:str, market:IMarket, strategy:Callable, freq='15 min', end:Optional[datetime]=None):
    _symbol = Symbol.objects.get_or_create(name=symbol, market=market.name)[0]
    session = Session.objects.create(
        symbol=_symbol,
        session_type=Session.Type.LIVE_BASIC,
        freq=freq,
        strategy_name=strategy.name,
        strategy_parameters=strategy.params,
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
        except MarketError:
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
                    size=last_order.capital,
                    price=last_order.price,
                    quantity=last_order.assets,
                    funds=last_order.capital,
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
                    size=last_order.capital,
                    price=last_order.price,
                    quantity=last_order.assets,
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


def sample_livetest():
    strg = get_strategy('v1')()
    market = get_market('MEXC')
    run_livetest('TARA-USDT', market, strg)


def create_objs():
    Market.objects.get_or_create(
        exchange_name=Market.Exchange.KUCOIN,
        friendly_name='KuCoin Unauthorized')


if __name__ == '__main__':
    create_objs()
    import json
    mc = json.load(open('api.json', 'r', encoding='ascii'))['BINANCE-TESTNET']
    ll = LiveLoop(
        'BTC-USDT', 
        get_market('BINANCE', mc),
        get_strategy('v1')(),
        capital_limit=100,
        asset_limit=100,
        freq='1 min')
    o = ll.force_buy()
    print(o)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        ll.stop()
        logger.info('KeyboardInterrupt detected, shutting down gracefully')
