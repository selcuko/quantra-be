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
    for i, row in ds.iterrows():
        if row['buy']:
            ok = testman.buy({'time': i, **row.to_dict()})
            if ok and verbose:
                #print(testman.summary())
                continue
        elif row['sell']:
            ok = testman.sell({'time': i, **row.to_dict()})
            if ok and verbose:
                print(testman.summary())
    testman.shutdown()

    return testman


if __name__ == '__main__':
    from strategy import StrategyV1, StrategyV2
    symbol = 'XRP-USDT'
    market = 'KUCOIN'
    ds = OHLCVDataset.from_csv(f'./data/{symbol}-{market}.csv')
    #strategy = StrategyV1()
    strategy = StrategyV2
    #download_symbol(market, symbol, start=datetime(2023, 7, 1))
    tm = analyze(ds, strategy, freq='15 min', symbol=symbol, market=market, verbose=True, start=datetime(2023, 7, 1), end=datetime(2023, 9, 13))
    #print(tm.summary())
    
