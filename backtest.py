from datetime import datetime
from download import download_symbol
from models import OHLCVDataset
from testman import TestManager

def analyze(ds:OHLCVDataset, strategy:callable, freq:str='15 min', start:datetime=None, end:datetime=None, symbol:str=None, market:str=None, verbose=False):
    """Analyze the dataset and return a report."""
    ds = ds.change(freq)
    ds = ds[start:end]
    ds = strategy(ds)

    testman = TestManager(symbol=symbol, market=market, strategy=strategy, start=start, end=end)
    last_price = None
    for i, row in ds.iterrows():
        last_price = row['close']
        if row['buy']:
            ok = testman.buy({'time': i, **row.to_dict()})
            if ok and verbose:
                print(testman.summary())
        elif row['sell']:
            ok = testman.sell({'time': i, **row.to_dict()})
            if ok and verbose:
                print(testman.summary())
    testman.shutdown()

    return testman


if __name__ == '__main__':
    from strategy import StrategyV1, StrategyV2
    symbol = 'ARB-USDT'
    market = 'BINANCE'
    ds = OHLCVDataset.from_csv(f'./data/{symbol}-{market}.csv')
    #download_symbol(market, symbol, start=datetime(2023, 7, 1))
    tm = analyze(ds, StrategyV2, freq='15 min', symbol=symbol, market=market, verbose=True, start=datetime(2023, 7, 1), end=datetime(2023, 9, 13))
    #print(tm.summary())
    
