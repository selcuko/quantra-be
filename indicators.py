import pandas as pd
import numpy as np
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
pd.options.mode.chained_assignment = None

# Calculate EMA from scratch (TradingView)
def calculate_ema(df, length  ):
    ## df['EMA_1'] = calculate_ema(df['close'], 15)
    df = df.dropna()
    alpha = 2 / (length + 1)
    ema = pd.Series(np.nan, index=df.index)
    ema[length-1] = df[:length].mean()
    for i in range(length, len(df)):
        ema[i] = alpha * df[i] + (1 - alpha) * ema[i-1]
    
    return ema


# Calculate SMA from scratch (TradingView)
def calculate_sma(df,  length):
    ## last_block['SMA_1'] = calculate_sma(last_block['close'], 15)
    df = df.dropna()
    sma = pd.Series(np.nan, index=df.index)
    sma[length-1] = df[:length].mean()
    for i in range(length, len(df)):
        sma[i] = sma[i-1] + (df[i] - df[i-length]) / length
    return sma


# Calculate RMA from scratch (TradingView)
def calculate_rma(df,  length):
    ## last_block['RMA_1'] = calculate_rma(last_block['close'], 15)
    alpha = 1 / length
    rma = pd.Series(np.nan, index=df.index)
    rma[length-1] = calculate_sma(df,  length).iloc[length-1]
    for i in range(length, len(df)):
        rma[i] = alpha * df[i] + (1 - alpha) * rma[i-1]
    return rma



########################################################################

def calculate_rsi(df, length):
    delta = df.diff()
    up, down = delta.copy(), delta.copy()
    up[up < 0] = 0
    down[down > 0] = 0

    average_gain = calculate_rma(up, length)
    average_loss = abs(calculate_rma(down, length))
    average_gain = average_gain.dropna()
    average_loss = average_loss.dropna()
    rs = average_gain / average_loss
    return 100 - (100 / (1 + rs))
########################################################################
def calculate_stoch(data, window):
    low_min  = data.rolling(window=window).min()
    high_max = data.rolling(window=window).max()

    return (data - low_min) / (high_max - low_min) * 100

def StochRSI(df, rsi_length=14,stoch_length=14, smoothK=3, smoothD=3, inplace=True):
    """Calculate StochRSI for given data."""
    if not inplace:
        df = df.copy()
    rsi = calculate_rsi(df['close'], int(rsi_length))
    df.loc[:, 'rsi'] = rsi
    k = calculate_stoch(rsi, int(stoch_length))
    k1 = calculate_sma(k, int(smoothK))
    d1 = calculate_sma(k1, int(smoothD))
    df.loc[:, 'stochrsi_k'] = k1
    df.loc[:, 'stochrsi_d'] = d1
    return df


def MACD(df, n_fast=12, n_slow=26, n_signal=9, inplace=True):
    """Calculate MACD, MACD Signal and MACD difference."""
    if not inplace:
        df = df.copy()
    ema_fast = calculate_ema(df['close'], int(n_fast))
    ema_slow = calculate_ema(df['close'], int(n_slow))
    df['macd'] = ema_fast - ema_slow
    df['macd_signal'] = calculate_ema(df['macd'], int(n_signal))
    df['macd_diff'] = df['macd'] - df['macd_signal']
    return df

def T3(df, n=7, b=0.7, inplace=True):
    """Calculate T3 for given data."""
    if not inplace:
        df = df.copy()
    c1 = -b*b*b
    c2 = 3*b*b + 3*b*b*b
    c3 = -6*b*b - 3*b - 3*b*b*b
    c4 = 1 + 3*b + b*b*b + 3*b*b

    ln = n
    e1 = calculate_ema(df['close'], int(ln))
    e2 = calculate_ema(e1, int(ln))
    e3 = calculate_ema(e2, int(ln))
    e4 = calculate_ema(e3, int(ln))
    e5 = calculate_ema(e4, int(ln))
    e6 = calculate_ema(e5, int(ln))

    df['t3'] = c1*e6 + c2*e5 + c3*e4 + c4*e3
    return df


