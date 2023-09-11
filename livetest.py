from datetime import datetime, timedelta
import time, sys
from markets import MarketError, get_market
from models import OHLCVDataset, interval_to_minutes
from strategy import StrategyV1
from testman import TestManager
from logger import logger

def run_livetest(symbol, market_name, strategy:callable, freq='15 min', end:datetime=None):
    # do pre checks
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

    price = None
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



if __name__ == '__main__':
    symbol = sys.argv[1] if len(sys.argv) > 1 else 'SUI-USDT'
    market = sys.argv[2] if len(sys.argv) > 2 else 'binance'
    run_livetest(symbol, market, freq='1 min', end=timedelta(minutes=5))
