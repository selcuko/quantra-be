from datetime import datetime, timedelta

import pandas as pd
from models import OHLCVDataset
from download import download_symbol, _drop_duplicates, _validate_file, _interpolate_gaps, _get_interpolated_lines
from strategy import get_strategy
from backtest import analyze
from livetest import run_livetest
from indicators import calculate_ema, StochRSI
import pandas_ta

from strategy.v1 import StrategyV1
from strategy.v2 import StrategyV2

symbol = 'XRP-USDT'
market = 'KUCOIN'
ds = OHLCVDataset.from_csv(f'data/{symbol}-{market}.csv')

strategy = StrategyV1()

ds1 = strategy(ds.copy())
ds2 = StrategyV2(ds.copy())

ds1 = pd.DataFrame(ds1)
ds2 = pd.DataFrame(ds2)
