import json
import threading
import time
from datetime import datetime, timedelta

import pytz
import django
django.setup()

from logger import logger
from markets import IMarket, MarketError, get_market
from models import OHLCVDataset, interval_to_minutes
from strategy import Strategy, get_strategy
from testman import TestManager
from quantapi.models import Order, Session, Signal, Subscription, User, Symbol, Market


class LiveLoop:
    def __init__(
            self,
            symbol:str, 
            market:IMarket, 
            strategy:Strategy,
            capital_limit:float,
            asset_limit:float,
            initiating_user:User=None,
            freq:str='15 min',
            end:datetime=None, 
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
        market = Market.objects.get(exchange_name=market.name)
        self.symbol = Symbol.objects.get_or_create(name=symbol, market=market)[0]
        self.session = Session.objects.create(
            symbol=self.symbol,
            session_type=Session.Type.LIVE_SANDBOX,
            freq=freq,
            strategy_name=strategy.name,
            strategy_parameters=strategy.params,
            planned_shutdown=end,
            status=Session.Status.ONGOING,
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
            commission=self.market.commission
        )
        self.loop_interval_s = interval_to_minutes(freq) * 60
        self.last_kline_dt = None
        self.session.notify(f'Initiating live test - hope the core is stable 🤞')
        

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
        last_order = None
        while not self.should_stop() and self.wait_next_candle() and not self.should_stop():
            self.handle_manual_overrides()

            last_klines = self.market.get_last_klines(self.symbol.name, self.freq)
            raw_dataset = OHLCVDataset(last_klines)
            strategy_dataset = self.strategy(raw_dataset)

            self.last_kline_dt = strategy_dataset.index[-1].to_pydatetime()
            last_kline = {'time': self.last_kline_dt.timestamp(), **strategy_dataset.iloc[-1].to_dict()}
            positive_buy_signal = last_kline['buy']
            positive_sell_signal = last_kline['sell']

            self.testman.update(last_kline)

            if positive_buy_signal:
                signal = Signal.objects.create(
                    session=self.session,
                    timestamp=self.last_kline_dt,
                    side=Signal.Side.BUY,
                    price=last_kline['close'],
                    raw=last_kline)
                self.session.notify_signal(signal)
                if not self.testman.bought:
                    last_order = self.market.place_market_order(self.symbol, 'buy', funds=self.testman.capital)
                    last_order.signal = signal
                    last_order.save()
                    self.session.notify_order(last_order)
                self.testman.buy(last_kline, sync=last_order)
            
            elif positive_sell_signal:
                signal = Signal.objects.create(
                    session=self.session,
                    timestamp=self.last_kline_dt,
                    side=Signal.Side.SELL,
                    price=last_kline['close'],
                    raw=last_kline)
                self.session.notify_signal(signal)
                if self.testman.bought:
                    last_order = self.market.place_market_order(self.symbol, 'sell', quantity=self.testman.assets)
                    last_order.signal = signal
                    last_order.save()
                    self.session.notify_order(last_order)
                self.testman.sell({'time': self.last_kline_dt, **last_kline.to_dict()}, sync=last_order)

            summary = self.testman.summary()
            logger.info(summary)
        self.running = False
        report = self.testman.shutdown(save=True)
        self.session.ended = datetime.now(tz=pytz.UTC)
        self.session.report = report
        self.session.status = Session.Status.COMPLETED
        self.session.save()
        self.session.notify_complete(f'Live loop completed, summary: {summary}')
        
    def handle_manual_overrides(self):
        """Handle manual overrides such as force buy, update capital limit etc."""
        pass

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

    def stop(self):
        self.will_stop = True
    
    def force_buy(self):
        raise NotImplementedError

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
        while True:
            if not self.thread.is_alive():
                logger.error(f'Thread ({self.thread.name}) died, exiting')
                break
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                break


def run_livetest(symbol:str, market:IMarket, strategy:callable, freq='15 min', end:datetime=None):
    symbol = Symbol.objects.get_or_create(name=symbol, market=market.name)[0]
    session = Session.objects.create(
        symbol=symbol,
        session_type=Session.Type.LIVE_BASIC,
        freq=freq,
        strategy_name=strategy.name,
        strategy_parameters=strategy.params,
        planned_shutdown=end,
        status=Session.Status.ONGOING,
    )
    testman = TestManager(symbol=symbol.name, market=market, live=True, strategy=strategy) # params are optional
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
                testman.buy({'time': ds.index[-1], **kline.to_dict()})
                last_order = testman.trades[-1]
                Order.objects.create(
                    oid=last_order.id,
                    size=last_order.capital,
                    price=last_order.price,
                    quantity=last_order.assets,
                    funds=last_order.capital,
                )
                    
        elif should_sell:
            signal = Signal.objects.create(
                session=session,
                timestamp=ds.index[-1],
                side=Signal.Side.SELL,
                price=kline['close'],
                raw=kline)
            if not testman.bought:
                testman.sell({'time': ds.index[-1], **kline.to_dict()})
                last_order = testman.trades[-1]
                Order.objects.create(
                    oid=last_order.id,
                    size=last_order.capital,
                    price=last_order.price,
                    quantity=last_order.assets,
                    funds=last_order.capital,
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
    run_livetest('TARA-USDT', 'MEXC', strg)


def create_objs():
    Market.objects.get_or_create(
        exchange_name=Market.Exchange.KUCOIN,
        friendly_name='KuCoin Unauthorized')


if __name__ == '__main__':
    create_objs()
    ll = LiveLoop(
        'BTC-USDT', 
        get_market('KUCOIN'), 
        get_strategy('v1')(), 
        capital_limit=100, 
        asset_limit=100,
        freq='1 min')
    ll.run()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        ll.stop()
        logger.info('KeyboardInterrupt detected, shutting down gracefully')
