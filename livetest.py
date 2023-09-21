from datetime import datetime, timedelta
import json
import time, sys
from markets import MarketError, get_market
from models import OHLCVDataset, interval_to_minutes
from strategy import get_strategy
from testman import TestManager
from logger import logger

def run_livetest(symbol, market_name, strategy:callable, freq='15 min', end:datetime=None):
    # do pre checks
    try:
        klines = get_market(market_name).get_last_klines(symbol, freq)
        ds = OHLCVDataset(klines)
        ds = strategy(ds)
    except:
        # calling the strategy is required to set it's name and params from inside..
        pass
    market = get_market(market_name)
    symbol = symbol.upper()
    testman = TestManager(symbol=symbol, market=market.name, live=True, strategy=strategy) # params are optional
    if isinstance(end, timedelta):
        end = datetime.now() + end
    
    logger.info(f'Running live test on {symbol} from {market.name} with freq {freq.replace(" ", "").upper()}, planned shutdown at {end}')
    def break_check():
        # more like brake check haha
        if end and datetime.now() > end:
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
        kline = ds.iloc[-1]
        if should_buy:
            testman.buy({'time': ds.index[-1], **kline.to_dict()})
        elif should_sell:
            testman.sell({'time': ds.index[-1], **kline.to_dict()})
        print(testman.summary())
        try:
            time.sleep(loop_interval)
        except KeyboardInterrupt:
            logger.info('KeyboardInterrupt detected, shutting down gracefully')
            break
    testman.shutdown()

def run_livetest_in_sandbox(symbol, market, config, strategy, freq='15 min', end:datetime=None):
    if not config.get('TESTNET'):
        raise ValueError('You can only run this live test in sandbox mode')
    if isinstance(end, timedelta):
        end = datetime.now() + end
    market = get_market(market, config)
    testman = TestManager(symbol=symbol, market=market.name, live=True, strategy=strategy, interval=freq) # params are optional
    loop_interval = interval_to_minutes(freq) * 60

    def break_check():
        if end:
            return end > datetime.now()
        return True

    while break_check():
        loop_start = time.time()
        klines = market.get_last_klines(symbol, freq)
        ds = OHLCVDataset(klines)
        ds = strategy(ds)
        should_buy = ds.iloc[-1]['buy']
        should_sell = ds.iloc[-1]['sell']
        kline = ds.iloc[-1]
        last_order = None

        if should_buy:
            if not testman.bought:
                last_order = market.place_market_order(symbol, 'buy', funds=testman.capital)
                print('Placed order', last_order)
                order = market.get_order(last_order.symbol, last_order.oid)
                print('Detail view', order)
            testman.buy({'time': ds.index[-1], **kline.to_dict()})
        elif should_sell:
            if testman.bought:
                last_order = market.place_market_order(symbol, 'sell', quantity=testman.assets)
                print('Placed order', last_order)
                order = market.get_order(last_order.symbol, last_order.oid)
                print('Detail view', order)
            testman.sell({'time': ds.index[-1], **kline.to_dict()})
        print(testman.summary())
        try:
            loop_end = time.time()
            loop_took = loop_end - loop_start
            time.sleep(loop_interval - loop_took)
        except KeyboardInterrupt:
            logger.info('KeyboardInterrupt detected, shutting down gracefully')
            break
    testman.shutdown()


def sample_livetest():
    strg = get_strategy('v1')()
    run_livetest('TARA-USDT', 'MEXC', strg)

def sample_livetest_sandbox():
    conf = json.load(open('api.json'))['BINANCE-TESTNET']
    strg = get_strategy('v1')()
    run_livetest_in_sandbox('XRP-USDT', 'BINANCE', conf, strg, freq='1 min')

if __name__ == '__main__':
    sample_livetest_sandbox()
