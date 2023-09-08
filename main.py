from markets import get_market
from datetime import datetime, timedelta
from models import OHLCVDataset
from pandas import DataFrame
from download import download_symbol
from pandas_ta import ema, macd, rsi, stoch, stochrsi, supertrend, vwap
import pandas as pd
from strategy import StrategyV1
from backtest import analyze
from livetest import run_livetest

download_symbol('binance', 'SUI-USDT', datetime(2023, 6, 1))
