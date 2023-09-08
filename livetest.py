from datetime import datetime
import time
from markets import get_market
from models import OHLCVDataset
from backtest import analyze
from strategy import StrategyV1
from testman import TestManager


def run_livetest(symbol, market_name, freq='15 min', end:datetime=None):
    # do pre checks
    market = get_market(market_name)
    testman = TestManager()
    
    def break_check():
        # more like brake check haha
        if end and datetime.now() > end:
            return True
        return False

    price = None

    while True:
        if break_check():
            break
        klines = market.get_last_klines(symbol, freq)
        ds = OHLCVDataset(klines)
        ds = StrategyV1(ds)
        should_buy = ds.iloc[-1]['buy']
        should_sell = ds.iloc[-1]['sell']
        price = ds.iloc[-1]['close']
        if should_buy:
            testman.buy(price)
        elif should_sell:
            testman.sell(price)
        print(testman.summary())
        time.sleep(60)
    testman.shutdown(price)



if __name__ == '__main__':
    run_livetest('BTC-USDT', 'binance', start=datetime(2023, 9, 6))
