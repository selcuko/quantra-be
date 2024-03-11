import django
django.setup()

import time
from datetime import datetime, timedelta
from typing import Callable, Optional

import pytz

from logger import logger
from markets import IMarket
from markets.errors import MarketAPIError
from models import OHLCVDataset, interval_to_minutes
from quantapi.models import MarketSymbol, Order, Session, Signal
from testman import TestManager


def run_livetest(symbol:str, market:IMarket, strategy:Callable, freq='15 min', end:Optional[datetime]=None):
    _symbol = MarketSymbol.objects.get_or_create(name=symbol, market=market.name)[0]
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
