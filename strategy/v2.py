from datetime import datetime, timedelta
from logger import logger
import pandas as pd
from indicators import StochRSI, T3, MACD
from models import OHLCVDataset

# disable pandas warnings
pd.options.mode.chained_assignment = None
# disable futurewarnings
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)



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


def StrategyV2(ds, params={}):
    params = {**default_params, **params}
    try:
        MACD(ds, n_fast=params['macd']['fast'], n_slow=params['macd']['slow'], n_signal=params['macd']['signal'], inplace=True)
        StochRSI(ds, rsi_length=params['stochrsi']['rsi_length'], stoch_length=params['stochrsi']['length'], smoothK=params['stochrsi']['k'], smoothD=params['stochrsi']['d'], inplace=True)
        T3(ds, n=params['t3']['length'], b=params['t3']['a'], inplace=True)
    except Exception as e:
        logger.error(f'Error in StrategyV2 while calculating indicators: {e!r}')
        logger.exception(e)
        raise e
    if not (
        'macd' in ds.columns
        and 'macd_signal' in ds.columns
        and 'macd_diff' in ds.columns
        and 'stochrsi_k' in ds.columns
        and 'stochrsi_d' in ds.columns
        and 't3' in ds.columns
    ):
        raise Exception('Error in StrategyV1 while calculating indicators: missing columns (this is probably due to dataset being too small)')
    
    ds['macd_buy'] = (ds['macd_diff'] >= 0) == (ds['macd_diff'].shift(1) < ds['macd_diff'])
    ds['macd_sell'] = (ds['macd_diff'] < 0) == (ds['macd_diff'].shift(1) >= ds['macd_diff'])

    ds['stochrsi_buy'] = ds['stochrsi_k'] > ds['stochrsi_d']
    ds['stochrsi_sell'] = ds['stochrsi_k'] < ds['stochrsi_d']

    ds['t3_buy'] = ds['t3'] > ds['t3'].shift(1)
    ds['t3_sell'] = ds['t3'] < ds['t3'].shift(1)

    ds['buy'] = ds['macd_buy'] & ds['stochrsi_buy'] & ds['t3_buy']
    ds['sell'] = ds['macd_sell'] & ds['stochrsi_sell'] & ds['t3_sell']

    return ds
