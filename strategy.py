from datetime import datetime, timedelta
from logger import logger
import pandas_ta as ta
import pandas as pd

from models import OHLCVDataset

# disable pandas warnings
pd.options.mode.chained_assignment = None

minL = 26


def _freq_to_timedelta(freq, minL):
    return {
        '1 min': timedelta(minutes=1),
        '3 min': timedelta(minutes=3),
        '5 min': timedelta(minutes=5),
        '15 min': timedelta(minutes=15),
        '30 min': timedelta(minutes=30),
        '1 hour': timedelta(hours=1),
        '2 hour': timedelta(hours=2),
        '4 hour': timedelta(hours=4),
        '6 hour': timedelta(hours=6),
        '8 hour': timedelta(hours=8),
        '12 hour': timedelta(hours=12),
        '1 day': timedelta(days=1),
        '3 day': timedelta(days=3),
        '1 week': timedelta(weeks=1),
        '1 month': timedelta(days=30),
    }[freq] * minL


def StrategyV1(ds):
    params = {
        'macd': {
            'fast': 12,
            'slow': 26,
            'signal': 9
        },
        'stochrsi': {
            'fastk_period': 14,
            'fastd_period': 3,
        },
        't3': {
            'length': 5,
            'volume_factor': 0.7
        }
    }
    try:
        ds.ta.macd(**params['macd'], append=True, col_names=('macd', 'macd_signal', 'macd_diff'))
        ds.ta.stochrsi(**params['stochrsi'], append=True, col_names=('stoch_rsi_fastk', 'stochrsi_fastd'))
        ds.ta.t3(**params['t3'], append=True, col_names=('t3',))
    except Exception as e:
        logger.error(f'Error in StrategyV1 while calculating indicators: {e!r}')
        logger.exception(e)
        raise e
    if not (
        'macd' in ds.columns
        and 'macd_signal' in ds.columns
        and 'macd_diff' in ds.columns
        and 'stoch_rsi_fastk' in ds.columns
        and 'stochrsi_fastd' in ds.columns
        and 't3' in ds.columns
    ):
        raise Exception('Error in StrategyV1 while calculating indicators: missing columns (this is probably due to dataset being too small)')
    
    ds['macd_buy'] = (ds['macd_diff'] >= 0) == (ds['macd_diff'].shift(1) < ds['macd_diff'])
    ds['macd_sell'] = (ds['macd_diff'] < 0) == (ds['macd_diff'].shift(1) >= ds['macd_diff'])

    ds['stochrsi_buy'] = ds['stoch_rsi_fastk'] > ds['stochrsi_fastd']
    ds['stochrsi_sell'] = ds['stoch_rsi_fastk'] < ds['stochrsi_fastd']

    ds['t3_buy'] = ds['t3'] > ds['t3'].shift(1)
    ds['t3_sell'] = ds['t3'] < ds['t3'].shift(1)

    ds['buy'] = ds['macd_buy'] & ds['stochrsi_buy'] & ds['t3_buy']
    ds['sell'] = ds['macd_sell'] & ds['stochrsi_sell'] & ds['t3_sell']

    return ds
