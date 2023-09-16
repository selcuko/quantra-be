from datetime import datetime, timedelta
import time, sys
from markets import MarketError, get_market
from models import OHLCVDataset, interval_to_minutes
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
    testman = TestManager(symbol=symbol, market=market.name, live=True, strategy=strategy) # params are optional
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
        order_id = None

        if should_buy:
            if not testman.bought:
                order_id = market.place_market_order(symbol, 'buy', funds=testman.capital)
                print('Placed order', order_id)
                order = market.get_order(order_id)
                print('Detail view', order)
            testman.buy({'time': ds.index[-1], **kline.to_dict()})
        elif should_sell:
            if testman.bought:
                order_id = market.place_market_order(symbol, 'sell', quantity=testman.assets)
                print('Placed order', order_id)
                order = market.get_order(order_id)
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


if __name__ == '__main__':
    from strategy import get_strategy
    symbol = sys.argv[1] if len(sys.argv) > 1 else 'SUI-USDT'
    market = sys.argv[2] if len(sys.argv) > 2 else 'binance'
    freq = sys.argv[3] if len(sys.argv) > 3 else '1 min'
    strategy = get_strategy(sys.argv[4] if len(sys.argv) > 4 else 'v1')()
    run_livetest(symbol, market, strategy=strategy, freq=freq)
