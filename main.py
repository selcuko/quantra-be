from datetime import datetime, timedelta
from models import OHLCVDataset
from download import download_symbol
from strategy import get_strategy
from backtest import analyze
from livetest import run_livetest

download_symbol('binance', 'SUI-USDT', datetime(2023, 6, 1))
ds = OHLCVDataset.from_csv('data/SUI-USDT-BINANCE.csv')
tm = analyze(ds, get_strategy('v1', {'t3': {'length': 10}}), freq='5 min', start=datetime(2023, 6, 1), end=datetime(2023, 9, 1))

