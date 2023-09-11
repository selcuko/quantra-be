from datetime import datetime, timedelta
from models import OHLCVDataset
from download import download_symbol
from strategy import get_strategy
from backtest import analyze
from livetest import run_livetest
from indicators import calculate_ema, StochRSI

ds = OHLCVDataset.from_csv('data/RNDR-USDT-BINANCE.csv')

ds1 = ds.copy()
ds2 = ds.copy()

st1 = get_strategy('v1')
st2 = get_strategy('v2')

res1 = analyze(ds1, st1)
res2 = analyze(ds2, st2)

print("StrategyV1:", res1.summary())
print("StrategyV2:", res2.summary())


