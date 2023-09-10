from datetime import datetime, timedelta
from models import OHLCVDataset
from download import download_symbol
from strategy import StrategyV1
from backtest import analyze
from livetest import run_livetest

download_symbol('binance', 'SUI-USDT', datetime(2023, 6, 1))
ds = OHLCVDataset.from_csv('data/SUI-USDT-BINANCE.csv')
tm = analyze(ds, StrategyV1, freq='1 week', start=datetime(2023, 6, 1), end=datetime(2023, 9, 1))

