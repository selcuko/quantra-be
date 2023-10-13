from datetime import datetime, timedelta
import json
import time
import pytz
from markets import Market, MarketError, get_market
from models import OHLCVDataset, interval_to_minutes
from strategy import Strategy, get_strategy
from testman import TestManager
from logger import logger
from datalayer import add_order, add_session, add_signal, db_session as sql_session
from datalayer import get_market as get_db_market
from datalayer import add_symbol as add_db_symbol

def run_livetest(symbol, market_name, strategy:callable, freq='15 min', end:datetime=None):
    # do pre checks
    try:
        klines = get_market(market_name).get_last_klines(symbol, freq)
        ds = OHLCVDataset(klines)
        ds = strategy(ds)
    except:
        # calling the strategy is required to set it's name and params from inside..
        pass
    market = get_market(market_name)
    symbol = symbol.upper()
    testman = TestManager(symbol=symbol, market=market.name, live=True, strategy=strategy) # params are optional
    if isinstance(end, timedelta):
        end = datetime.now(tz=pytz.UTC) + end
    
    logger.info(f'Running live test on {symbol} from {market.name} with freq {freq.replace(" ", "").upper()}, planned shutdown at {end}')
    def break_check():
        # more like brake check haha
        if end and datetime.now(tz=pytz.UTC) > end:
            return True
        return False

    loop_interval = interval_to_minutes(freq) * 60

    while True:
        if break_check():
            break
        try:
            klines = market.get_last_klines(symbol, freq)
        except MarketError:
            logger.fatal(f'Fatal error halted program while fetching klines for {symbol} from {market.name}')
            testman.shutdown()
            return
        ds = OHLCVDataset(klines)
        ds = strategy(ds)
        should_buy = ds.iloc[-1]['buy']
        should_sell = ds.iloc[-1]['sell']
        kline = ds.iloc[-1]
        if should_buy:
            testman.buy({'time': ds.index[-1], **kline.to_dict()})
        elif should_sell:
            testman.sell({'time': ds.index[-1], **kline.to_dict()})
        print(testman.summary())
        try:
            time.sleep(loop_interval)
        except KeyboardInterrupt:
            logger.info('KeyboardInterrupt detected, shutting down gracefully')
            break
    testman.shutdown()

def run_livetest_in_sandbox(symbol, market:Market, strategy:Strategy, freq='15 min', end:datetime=None, capital=100):
    print(f'Running live test on {symbol} from {market.name} with freq {freq.replace(" ", "").upper()}, planned shutdown at {end}')
    db_market = get_db_market(market.name)
    db_symbol = add_db_symbol(symbol, db_market)
    db_session = add_session(db_symbol, db_market, test_type='live.sandbox', freq=freq)

    if isinstance(end, timedelta):
        end = datetime.now(tz=pytz.UTC) + end

    assert market.testnet, f'This market config ({market.name}) is not using a testnet'
    assert market.spot_trading_enabled, f'Spot trading is not enabled for this market ({market.name})'
    assert capital > 0, 'Capital must be greater than 0'
    assert capital < market.capital, f'Capital must be less than account funds of ${market.capital:.2f}'

    testman = TestManager(
        symbol=symbol, 
        market=market, 
        type='live.sandbox', 
        strategy=strategy, 
        interval=freq,
        capital=capital,
        commission=market.commission)
    last_kline_ts = None
    loop_interval_s = interval_to_minutes(freq) * 60

    def break_check():
        """Wait before the first seconds of next candle"""
        if end:
            return end > datetime.now(tz=pytz.UTC)
        if last_kline_ts: # calculate time to the next minute
            residue = last_kline_ts + loop_interval_s + 5 - time.time()
            try:
                if residue > 0:
                    time.sleep(residue)
                else:
                    # new candle is not available yet
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info('KeyboardInterrupt detected, shutting down gracefully')
                db_session.ended = datetime.now(tz=pytz.UTC)
                sql_session.commit()
                return False
        return True

    while break_check():        
        last_klines = market.get_last_klines(symbol, freq)
        raw_ds = OHLCVDataset(last_klines)
        stg_ds = strategy(raw_ds)

        last_kline = stg_ds.iloc[-1]
        should_buy = last_kline['buy']
        should_sell = last_kline['sell']
        last_order = None
        testman.update(kline={'time': stg_ds.index[-1], **last_kline.to_dict()})
        if should_buy:
            db_signal = add_signal(
                symbol=db_symbol, 
                market=db_market, 
                timestamp=stg_ds.index[-1], 
                side='buy', 
                price=last_kline['close'], 
                rawrow=last_kline.to_dict()
            )
            if not testman.bought:
                last_order = market.place_market_order(symbol, 'buy', funds=testman.capital)
                db_order = add_order(
                    signal=db_signal, 
                    side='buy', 
                    price=last_order.price,
                    quantity=last_order.deal_funds,
                    size=last_order.deal_size,
                    order_type=last_order.type,
                    status=last_order.status,
                    timestamp=last_order.timestamp
                )
                if not last_order.status in ['ACTIVE', 'FILLED']:
                    logger.error(f'Order {last_order.oid} failed to fill, status: {last_order.status}')
            testman.buy({'time': stg_ds.index[-1], **last_kline.to_dict()}, sync=last_order)
        elif should_sell:
            db_signal = add_signal(
                symbol=db_symbol, 
                market=db_market, 
                timestamp=stg_ds.index[-1], 
                side='sell', 
                price=last_kline['close'], 
                rawrow=last_kline.to_dict()
            )
            if testman.bought:
                last_order = market.place_market_order(symbol, 'sell', quantity=testman.assets)
                db_order = add_order(
                    signal=db_signal, 
                    side='sell', 
                    price=last_order.price,
                    quantity=last_order.deal_funds,
                    size=last_order.deal_size,
                    order_type=last_order.type,
                    status=last_order.status,
                    timestamp=last_order.timestamp
                )
                if not last_order.status in ['ACTIVE', 'FILLED']:
                    logger.error(f'Order {last_order.oid} failed to fill, status: {last_order.status}')
            testman.sell({'time': stg_ds.index[-1], **last_kline.to_dict()}, sync=last_order)
        print(testman.summary())
        last_kline_ts = stg_ds.index[-1].timestamp()
    testman.shutdown()
    # set session end time and save
    db_session.ended = datetime.now(tz=pytz.UTC)
    sql_session.commit()


def sample_livetest():
    strg = get_strategy('v1')()
    run_livetest('TARA-USDT', 'MEXC', strg)

def sample_livetest_sandbox():
    conf = json.load(open('api.json'))['BINANCE-TESTNET']
    strg = get_strategy('v1')()
    run_livetest_in_sandbox('XRP-USDT', get_market('BINANCE', conf), strg, freq='1 min')

if __name__ == '__main__':
    sample_livetest_sandbox()
