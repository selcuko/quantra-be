from datetime import datetime, timedelta
import os
from markets import get_market
from logger import logger


def _get_filename(market_name, symbol):
    return f'./data/{symbol}-{market_name}.csv'


def _validate_file(filename):
    """Returns last datetime on record"""
    if not os.path.exists(filename):
        return True
    infile = open(filename, 'r')
    notempty = False
    last = None
    logger.debug(f'Validating file {filename}')
    for i, line in enumerate(infile):
        notempty = True
        if last and int(line.split(',')[0]) - 60 != last:
            logger.error(f'Inconsistent timestamps in file. Please fix or delete file {filename}')
            logger.error(f'Erroneous line no: {i+1}  -->  {line}')
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
    outfile = open(_get_filename(market_name, symbol), 'a+')
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
