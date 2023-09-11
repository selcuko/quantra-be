from datetime import datetime, timedelta
from logger import logger
import pandas_ta as ta
import pandas as pd

from models import OHLCVDataset

# disable pandas warnings
pd.options.mode.chained_assignment = None

minL = 26


default_params = {
        'macd': {
            'fast': 12,
            'slow': 26,
            'signal': 9
        },
        'stochrsi': {
            'length': 14,
            'rsi_length': 14,
            'k': 3,
            'd': 3
        },
        't3': {
            'length': 5,
            'a': 0.618
        }
    }


def StrategyV1(ds, params={}):
    params = {**default_params, **params}
    StrategyV1.name = 'StrategyV1.Lisa.PandasTA'
    StrategyV1.params = params
    try:
        ds.ta.macd(**params['macd'], append=True, col_names=('macd', 'macd_signal', 'macd_diff'))
        ds.ta.stochrsi(**params['stochrsi'], append=True, col_names=('stochrsi_fastk', 'stochrsi_fastd'))
        ds.ta.t3(**params['t3'], append=True, col_names=('t3',))
    except Exception as e:
        logger.error(f'Error in StrategyV1 while calculating indicators: {e!r}')
        logger.exception(e)
        raise e
    if not (
        'macd' in ds.columns
        and 'macd_signal' in ds.columns
        and 'macd_diff' in ds.columns
        and 'stochrsi_fastk' in ds.columns
        and 'stochrsi_fastd' in ds.columns
        and 't3' in ds.columns
    ):
        raise Exception('Error in StrategyV1 while calculating indicators: missing columns (this is probably due to dataset being too small)')
    
    ds['macd_buy'] = (ds['macd_diff'] >= 0) == (ds['macd_diff'].shift(1) < ds['macd_diff'])
    ds['macd_sell'] = (ds['macd_diff'] < 0) == (ds['macd_diff'].shift(1) >= ds['macd_diff'])

    ds['stochrsi_buy'] = ds['stochrsi_fastk'] > ds['stochrsi_fastd']
    ds['stochrsi_sell'] = ds['stochrsi_fastk'] < ds['stochrsi_fastd']

    ds['t3_buy'] = ds['t3'] > ds['t3'].shift(1)
    ds['t3_sell'] = ds['t3'] < ds['t3'].shift(1)

    ds['buy'] = ds['macd_buy'] & ds['stochrsi_buy'] & ds['t3_buy']
    ds['sell'] = ds['macd_sell'] & ds['stochrsi_sell'] & ds['t3_sell']

    return ds
