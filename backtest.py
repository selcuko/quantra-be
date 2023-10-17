from datetime import datetime
from markets import Market
from models import OHLCVDataset
from testman import TestManager
from datalayer import add_session, db_session as sql_session
from datalayer import get_market as get_db_market
from datalayer import add_symbol as add_db_symbol

def analyze(ds:OHLCVDataset, strategy:callable, freq:str='15 min', start:datetime=None, end:datetime=None, symbol:str=None, market:Market=None, verbose=False, capital:float=1000):
    """Analyze the dataset and return a report."""
    print(f'Starting backtest for {symbol}@{market.name} from {start} to {end}')
    db_market = get_db_market(market.name)
    db_symbol = add_db_symbol(symbol, db_market)
    db_session = add_session(
        symbol=db_symbol,
        market=db_market,
        strategy=strategy.name,
        strategy_parameters=strategy.params,
        test_type='backtest',
        freq=freq,
        planned_shutdown=end)
    
    ds = ds.change(freq)
    ds = ds[start:end]
    ds = strategy(ds)

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
    db_session.status = 'completed'
    db_session.end = datetime.utcnow()
    db_session.testman_dir = testman_dir
    sql_session.commit()
    return testman


if __name__ == '__main__':
    from strategy import get_strategy
    from markets import get_market
    symbol = 'XRP-USDT'
    market = get_market('KUCOIN')
    ds = OHLCVDataset.from_csv(f'./data/{symbol}-{market.name}.csv')
    strategy = get_strategy('v2')()
    tm = analyze(ds, strategy, freq='15 min', symbol=symbol, market=market, verbose=True, start=datetime(2023, 7, 1), end=datetime(2023, 9, 13))
    
