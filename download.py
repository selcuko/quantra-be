from datetime import datetime, timedelta
import os, sys

import pytz
from markets import get_market
from logger import logger


def _get_filename(market_name, symbol):
    return f'./data/{symbol.upper()}-{get_market(market_name).name}.csv'


def _drop_duplicates(filename):
    infile = open(filename, 'r')
    if os.path.exists(filename + '.tmp'):
        os.remove(filename + '.tmp')
    outfile = open(filename + '.tmp', 'w')
    last_ts = None
    for i, line in enumerate(infile):
        ts = int(line.split(',')[0])
        if not last_ts or ts != last_ts:
            outfile.write(line)
        last_ts = ts
    infile.close()
    outfile.close()
    os.remove(filename)
    os.rename(filename + '.tmp', filename)


def _get_interpolated_lines(l0, l1):
    t0, o0, h0, l0, c0, v0 = l0.replace('\n', '').split(',')
    t1, o1, h1, l1, c1, v1 = l1.replace('\n', '').split(',')
    t0, o0, h0, l0, c0, v0 = int(t0), float(o0), float(h0), float(l0), float(c0), float(v0)
    t1, o1, h1, l1, c1, v1 = int(t1), float(o1), float(h1), float(l1), float(c1), float(v1)
    t_diff = (t1 - t0) / 60
    o_diff = (o1 - o0) / t_diff
    h_diff = (h1 - h0) / t_diff
    l_diff = (l1 - l0) / t_diff
    c_diff = (c1 - c0) / t_diff
    v_diff = (v1 - v0) / t_diff
    lines = []
    for i in range(1, int(t_diff)):
        line = f'{t0 + i * 60},{o0 + i * o_diff},{h0 + i * h_diff},{l0 + i * l_diff},{c0 + i * c_diff},{v0 + i * v_diff}\n'
        lines.append(line)
    return lines


def _interpolate_gaps(filename):
    infile = open(filename, 'r')
    if os.path.exists(filename + '.tmp'):
        os.remove(filename + '.tmp')
    outfile = open(filename + '.tmp', 'w')

    last_ts = None
    last_line = None
    for i, line in enumerate(infile):
        ts = int(line.split(',')[0])
        if not last_ts or ts == last_ts + 60:
            outfile.write(line)
        else:
            lines = _get_interpolated_lines(last_line, line)
            for _newl in lines:
                outfile.write(_newl)
            outfile.write(line)
        last_ts = ts
        last_line = line
    infile.close()
    outfile.close()
    os.remove(filename)
    os.rename(filename + '.tmp', filename)


def _get_starting_point(filename):
    if not os.path.exists(filename):
        return None
    with open(filename, 'r') as infile:
        for line in infile:
            return datetime.fromtimestamp(int(line.split(',')[0]), tz=pytz.UTC)


def _validate_file(filename, interpolate=True, drop_duplicates=True):
    """Returns last datetime on record"""
    if not os.path.exists(filename):
        return True
    infile = open(filename, 'r')
    notempty = False
    last = None
    logger.debug(f'Validating file {filename}')
    for i, line in enumerate(infile):
        notempty = True
        ts = int(line.split(',')[0])
        if last and ts - 60 != last:
            if ts == last:
                if drop_duplicates:
                    logger.debug(f'Duplicate candles detected in file {filename}:{i+1}, fixing it by dropping duplicates.')
                    infile.close()
                    _drop_duplicates(filename)
                    return _validate_file(filename, interpolate, drop_duplicates)
                else:
                    logger.error(f'Duplicate candles detected in file {filename}:{i+1} but drop duplicates is disabled.')
                    return False
            elif (ts - last) % 60:
                logger.error(f'Found an irregular discontinuity at line {i+1}, halted.')
                return False
            elif ts - last > 60:
                if interpolate:
                    logger.debug(f'Gaps detected in file {filename}:{i+1}, fixing it by interpolating.')
                    infile.close()
                    _interpolate_gaps(filename)
                    return _validate_file(filename, interpolate, drop_duplicates)
                else:
                    logger.error(f'Gaps detected in file {filename}:{i+1} but interpolation is disabled.')
                    return False
        last = int(line.split(',')[0])
    logger.debug(f'File {filename} is valid.')
    if notempty:
        return datetime.fromtimestamp(int(line.split(',')[0]) + 60, tz=pytz.UTC).replace(second=0, microsecond=0)
    return True


def _handle_earlier_starting(market_name, symbol, start, lasttime):
    filename = _get_filename(market_name, symbol)
    os.replace(filename, filename + '.tmp')
    download_symbol(market_name, symbol, start, end=lasttime)
    with open(filename + '.tmp', 'r') as infile:
        with open(filename, 'a+') as outfile:
            for line in infile:
                outfile.write(line)
    os.remove(filename + '.tmp')


def download_symbol(market_name:str, symbol:str, start:datetime, end:datetime=None, interpolate=True, drop_duplicates=True):
    market = get_market(market_name)
    symbol = symbol.upper()
    lasttime = _validate_file(_get_filename(market.name, symbol), interpolate, drop_duplicates)
    starting = _get_starting_point(_get_filename(market.name, symbol))
    if starting and start < starting:
        logger.info(f'Starting date {start} is earlier than first kline on record {starting}.')
        _handle_earlier_starting(market.name, symbol, start, starting)
        return download_symbol(market_name, symbol, lasttime, end)
    empty_file = False
    if lasttime:
        if isinstance(lasttime, datetime):
            logger.debug(f'Last kline on record is {lasttime}, continuing from there.')
            start = lasttime
        else:
            empty_file = True
            logger.debug('File is empty. Starting from scratch.')
    else:
        return
    if not os.path.exists('./data'):
        os.mkdir('./data')
    outfile = open(_get_filename(market.name, symbol), 'a+')
    prev_batch_end = start = start.replace(second=0, microsecond=0)
    new_klines = 0

    logger.info(f'Downloading {symbol} from {market.name} starting from {start} to {end}.')

    while True:
        if end and prev_batch_end > end:
            break
        klines = market.get_klines(symbol, '1 min', prev_batch_end)
        if len(klines) == 0:
            if empty_file:
                logger.error('There are no records of {symbol} on {market.name} at {prev_batch_end}. Please confirm your settings.')
            break
        empty_file = False
        if prev_batch_end == klines[-1][0]:
            break
        prev_batch_end = klines[-1][0] + timedelta(minutes=1)
        for kline in klines:
            new_klines += 1
            line = f'{int(kline[0].timestamp())},{kline[1]},{kline[2]},{kline[3]},{kline[4]},{kline[5]}\n'
            outfile.write(line)
        logger.info(f'[DownloadInProgress][{datetime.now(tz=pytz.UTC)}] Klines: {new_klines} | Last kline: {klines[-1][0]}')
    if new_klines: print()
    outfile.close()
    validation_ok = _validate_file(_get_filename(market.name, symbol), interpolate, drop_duplicates)
    if not validation_ok:
        logger.error(f'Validation with settings interpolate={interpolate} and drop duplicates={drop_duplicates} failed. Please check your file.')
        return
    logger.info(f'Download OK ({new_klines} new klines), see file {_get_filename(market.name, symbol)}')
    return _get_filename(market.name, symbol)


if __name__ == '__main__':
    symbol = sys.argv[1] if len(sys.argv) > 1 else 'btc-usdt'
    market = sys.argv[2] if len(sys.argv) > 2 else 'binance'
    download_symbol(market, symbol, datetime(2023, 1, 10), end=datetime(2023, 8, 25), interpolate=False, drop_duplicates=False)
