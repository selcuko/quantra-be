from datetime import datetime
import json
from typing import Optional
import threading

from download import download_symbol
from markets import IMarket
from models import OHLCVDataset
from strategy import get_strategy
from strategy.interface import Strategy
from testman import TestManager
from quantapi.models import Backtest, Strategy as StrategyModel

from logger import logger

def analyze(ds:OHLCVDataset, symbol:str, market:IMarket, strategy:Strategy, freq:str='15 min', start:Optional[datetime]=None, end:Optional[datetime]=None, verbose=False, capital:float=1000, backtest=None):
    """Analyze the dataset and return a report."""
    print(f'Starting backtest for {symbol}@{market} from {start} to {end}')
    if backtest is None:
        backtest = Backtest.objects.create(
            start=start,
            end=end,
            freq=freq,
            symbol=symbol,
            market=str(market),
            status='INIT'
        )
    if end is None:
        end = datetime.now(tz=None)
    else:
        end = end.replace(tzinfo=None)
    start = start.replace(tzinfo=None)
    try:
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
            commission={'buyer': 0.002, 'seller': 0.002},
            assets=0)
        backtest.status = Backtest.Status.ONGOING
        backtest.save()
        for i, row in ds.iterrows():
            if row['buy']:
                ok = testman.buy({'time': i, **row.to_dict()})
                if ok and verbose:
                    print(testman.summary())
            elif row['sell']:
                ok = testman.sell({'time': i, **row.to_dict()})
                if ok and verbose:
                    print(testman.summary())
        
        report = testman.shutdown()
        backtest.status = Backtest.Status.COMPLETED
        backtest.report = report
        backtest.save()
    except Exception as e:
        logger.error(f'Error while backtesting {symbol}@{market}', exc_info=True)
        backtest.status = Backtest.Status.ERROR
        backtest.report = repr(e)
        backtest.save()
    return backtest


def async_analyze(**kwargs):
    backtest = Backtest.objects.create(
            start=kwargs['start'],
            end=kwargs.get('end') or None,
            freq=kwargs['freq'],
            symbol=kwargs['symbol'],
            market=kwargs['market'],
            status='INIT' )
    def download_and_analyze():
        try:
            strategy_name = kwargs.get('strategy_name', 'v1')
            strategy = get_strategy(strategy_name)()
            if not (strategy_model := StrategyModel.objects.filter(name=strategy_name).first()):
                strategy_model = StrategyModel.objects.create(name=strategy_name, parameters=json.dumps(strategy.params))
                strategy_model.save()
            else:
                strategy.params = json.loads(strategy_model.parameters)
        except Exception as e:
            logger.error(f'Error while loading strategy {kwargs.get("strategy_name", "v1")}', exc_info=True)
            backtest.status = Backtest.Status.ERROR
            backtest.report = repr(e)
            backtest.save()
            return
        download_symbol(kwargs['market'], kwargs['symbol'], kwargs['start'], kwargs.get('end'))
        ds = OHLCVDataset.from_csv(f'./data/{kwargs["symbol"]}-{kwargs["market"]}.csv')
        analyze(ds, symbol=kwargs['symbol'], market=kwargs['market'], strategy=strategy, freq=kwargs['freq'], start=kwargs['start'], end=kwargs.get('end'), backtest=backtest)
    analyze_thread = threading.Thread(target=download_and_analyze)
    analyze_thread.start()
    return backtest


if __name__ == '__main__':
    from markets import get_market
    symbol = 'XRP-USDT'
    market = get_market('KUCOIN')
    ds = OHLCVDataset.from_csv(f'./data/{symbol}-{market.name}.csv', candle_type='heikin_ashi')
    strategy = get_strategy('v1')()
    tm = analyze(
        ds=ds, 
        strategy=strategy, 
        freq='15 min', 
        symbol=symbol, 
        market=market, 
        verbose=True, 
        start=datetime(2023, 7, 1), 
        end=datetime(2023, 9, 13))
