from datetime import datetime
from models import OHLCVDataset
from strategy import StrategyV1
from testman import TestManager

def analyze(ds:OHLCVDataset, strategy:callable, freq:str='15 min', start:datetime=None, end:datetime=None):
    """Analyze the dataset and return a report."""
    ds = ds.change(freq)
    ds = strategy(ds)
    ds = ds[start:end]

    testman = TestManager()
    last_price = None
    for i, row in ds.iterrows():
        last_price = row['close']
        if row['buy']:
            testman.buy(last_price)

        elif row['sell']:
            testman.sell(last_price)
    testman.shutdown(last_price)

    print(testman.summary())
    return testman


if __name__ == '__main__':
    from strategy import StrategyV1
    ds = OHLCVDataset.from_csv('./data/BTC-USDT-BINANCE.csv')
    strategy = StrategyV1
    tm = analyze(ds, strategy, freq='1 min')
    
