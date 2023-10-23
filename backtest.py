import django
django.setup()

from datetime import datetime
from typing import Optional

from markets import IMarket
from models import OHLCVDataset
from quantapi.models import Market, Session, Symbol
from strategy.interface import Strategy
from testman import TestManager


def analyze(ds:OHLCVDataset, symbol:str, market:IMarket, strategy:Strategy, freq:str='15 min', start:Optional[datetime]=None, end:Optional[datetime]=None, verbose=False, capital:float=1000):
    """Analyze the dataset and return a report."""
    print(f'Starting backtest for {symbol}@{market.name} from {start} to {end}')
    _market = Market.objects.get(exchange_name=market.name)
    _symbol = Symbol.objects.get_or_create(name=symbol, market=_market)[0]
    
    ds = ds.change(freq)
    ds = ds[start:end]
    ds = strategy(ds)
    session = Session.objects.create(
            session_type=Session.Type.BACKTEST,
            symbol=_symbol,
            freq=freq,
            started=ds.index[0],
            ended=ds.index[-1],
            strategy_name=strategy.name,
            strategy_parameters=strategy.params,
            status=Session.Status.ONGOING,
        )
    testman = TestManager(
        symbol=symbol, 
        market=market, 
        strategy=strategy, 
        start=start, 
        end=end, 
        interval=freq, 
        capital=capital, 
        type='backtest',
        commission={'buyer': 0.002, 'seller': 0.002})

    for i, row in ds.iterrows():
        if row['buy']:
            ok = testman.buy({'time': i, **row.to_dict()})
            if ok and verbose:
                print(testman.summary())
        elif row['sell']:
            ok = testman.sell({'time': i, **row.to_dict()})
            if ok and verbose:
                print(testman.summary())
    
    testman_dir = testman.shutdown()
    session.status = Session.Status.COMPLETED
    session.report = testman_dir
    session.save()
    return testman


if __name__ == '__main__':
    from markets import get_market
    from strategy import get_strategy
    symbol = 'XRP-USDT'
    market = get_market('KUCOIN')
    ds = OHLCVDataset.from_csv(f'./data/{symbol}-{market.name}.csv')
    strategy = get_strategy('v2')()
    tm = analyze(
        ds=ds, 
        strategy=strategy, 
        freq='15 min', 
        symbol=symbol, 
        market=market, 
        verbose=True, 
        start=datetime(2023, 7, 1), 
        end=datetime(2023, 9, 13))
