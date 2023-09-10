from datetime import datetime, timedelta
import time
import requests, os
from backtest import analyze
from download import download_symbol
from models import OHLCVDataset
from strategy import StrategyV1
from logger import logger
from testman import TestManager

token = 'REDACTED'
queue = []
lui_path = 'tg_last_update_id.txt'
last_update_id = int(open(lui_path, 'r').read()) if os.path.exists(lui_path) else None

def send_message(chat_id, text):
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    data = {'chat_id': chat_id, 'text': text}
    requests.post(url, data=data)

def update_queue(chat_id, text):
    global queue
    queue.append((chat_id, text))

def clean_text(text):
    assert len(text.split(',')) == 3, 'Text must be in format: symbol,market,freq (e.g. SUI-USDT,binance,15 min)'
    return text

def poll_messages():
    global last_update_id
    params = {'offset': last_update_id + 1} if last_update_id else {}
    response = requests.get(f'https://api.telegram.org/bot{token}/getUpdates', params=params).json()
    for update in response['result']:
        last_update_id = update['update_id']
        open(lui_path, 'w').write(str(last_update_id))
        if 'message' in update:
            chat_id = update['message']['chat']['id']
            text = update['message']['text']
            try:
                ct = clean_text(text)
            except AssertionError as e:
                send_message(chat_id, e)
                continue
            update_queue(chat_id, ct)

def process_queue():
    global queue
    while len(queue) > 0:
        chat_id, text = queue.pop(0)
        symbol, market, freq = text.split(',')
        response = process_request(symbol, market, freq)
        send_message(chat_id, response)

def process_request(symbol, market, freq) -> TestManager:
    try:
        filedir = download_symbol(market, symbol, datetime.now()-timedelta(days=30))
        if not filedir:
            return 'Error downloading symbol data, contact your developer and check logs.'
        ds = OHLCVDataset.from_csv(filedir)
        ds = ds[datetime.now()-timedelta(days=30):]
        testman = analyze(ds, strategy=StrategyV1, freq=freq)    
        return testman.summary() + '\n\n' + f'Test took place between these dates: \n{ds.index[0]}\n{ds.index[-1]}'
    except Exception as e:
        logger.error(e, exc_info=True)
        return f'Error while processing request: {e}'

if __name__ == '__main__':
    while True:
        poll_messages()
        process_queue()
        time.sleep(1)