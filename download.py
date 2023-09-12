from datetime import datetime, timedelta
import os, sys
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
        else:
            print('Found duplicate at line', i+1)
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
                logger.debug(f'Found duplicate at line {i+1}')
                if drop_duplicates:
                    logger.debug(f'Will drop all duplicates')
                    infile.close()
                    _drop_duplicates(filename)
                    return _validate_file(filename, interpolate, drop_duplicates)
                else:
                    logger.error(f'Will not drop duplicates')
                    return False
            elif (ts - last) % 60:
                logger.error(f'Found an irregular discontinuity at line {i+1}')
                return False
            elif ts - last > 60:
                logger.debug(f'Found gap at line {i+1}')
                if interpolate:
                    logger.debug(f'Will interpolate gaps')
                    infile.close()
                    _interpolate_gaps(filename)
                    return _validate_file(filename, interpolate, drop_duplicates)
                else:
                    logger.error(f'Will not interpolate gaps')
                    return False
        last = int(line.split(',')[0])
    logger.debug(f'File {filename} is valid.')
    if notempty:
        return datetime.fromtimestamp(int(line.split(',')[0]) + 60).replace(second=0, microsecond=0)
    return True
        

def download_symbol(market_name:str, symbol:str, start:datetime):
    market = get_market(market_name)
    symbol = symbol.upper()
    print(f'Download {symbol} from {market.name} starting from {start}')
    lasttime = _validate_file(_get_filename(market.name, symbol))
    empty_file = False
    if lasttime:
        if isinstance(lasttime, datetime):
            print(f'Last time on record: {lasttime}')
            print('Overwriting start time to last time on record.')
            start = lasttime
        else:
            empty_file = True
            print('File is empty. Starting from scratch.')
    else:
        return
    if not os.path.exists('./data'):
        os.mkdir('./data')
    outfile = open(_get_filename(market.name, symbol), 'a+')
    prev_batch_end = start = start.replace(second=0, microsecond=0)
    new_klines = 0

    while True:
        klines = market.get_klines(symbol, '1 min', prev_batch_end)
        if len(klines) == 0:
            if empty_file:
                print('No data found. Please check your symbol, start date and market name.')
            print(f'Finished, {new_klines} new klines downloaded.')
            break
        empty_file = False
        if prev_batch_end == klines[-1][0]:
            print(f'Finished, {new_klines} new klines downloaded.')
            break
        prev_batch_end = klines[-1][0] + timedelta(minutes=1)
        for kline in klines:
            new_klines += 1
            line = f'{int(kline[0].timestamp())},{kline[1]},{kline[2]},{kline[3]},{kline[4]},{kline[5]}\n'
            outfile.write(line)
        print(f'[DownloadInProgress][{datetime.now()}] Klines: {new_klines} | Last kline: {klines[-1][0]}')
    outfile.close()
    print('Download finished. Validating file...')
    validation_ok = _validate_file(_get_filename(market.name, symbol))
    if not validation_ok:
        print('Validation failed. Please fix the discrepancies or delete the file.')
        return
    print('OK')
    return _get_filename(market.name, symbol)


if __name__ == '__main__':
    symbol = sys.argv[1] if len(sys.argv) > 1 else 'btc-usdt'
    market = sys.argv[2] if len(sys.argv) > 2 else 'binance'
    download_symbol(market, symbol, datetime(2023, 1, 1))