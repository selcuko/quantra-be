from datetime import datetime, timedelta
import json
import time
import pytz
from dbops import DBUser
from markets import Market, MarketError, get_market
from models import OHLCVDataset, interval_to_minutes
from strategy import Strategy, get_strategy
from testman import TestManager
from logger import logger
from datalayer import add_order, add_session, add_signal, add_subscription, db_session as sql_session, get_user
from datalayer import get_market as get_db_market
from datalayer import add_symbol as add_db_symbol
import threading


class LiveLoop:
    def __init__(
            self,
            symbol:str, 
            market:Market, 
            strategy:Strategy,
            capital_limit:float,
            asset_limit:float,
            initiating_user:DBUser=None,
            freq:str='15 min',
            end:datetime=None, 
        ) -> None:
        self.will_stop = False
        self.symbol = symbol
        self.market = market
        self.strategy = strategy
        self.freq = freq
        self.end = end
        self.capital_limit = capital_limit
        self.asset_limit = asset_limit
        self.thread = None
        self.running = False
        self.db_market = get_db_market(market.name)
        self.db_symbol = add_db_symbol(symbol, self.db_market)
        self.db_session = add_session(
            symbol=self.db_symbol,
            market=self.db_market,
            strategy=strategy.name,
            strategy_parameters=strategy.params,
            test_type='live.sandbox',
            freq=freq,
            status='planned',
            planned_shutdown=end
        )
        if initiating_user:
            self.db_user = initiating_user
        else:
            logger.warning('No initiating user provided, using default user (id=1)')
            self.db_user = get_user('master')
        add_subscription(self.db_user, self.db_session)

        self.testman = TestManager(
            symbol=symbol, 
            market=market, 
            type='live.sandbox', 
            strategy=strategy, 
            interval=freq,
            capital=capital_limit,
            commission=market.commission
        )
        self.loop_interval_s = interval_to_minutes(freq) * 60
        self.last_kline_dt = None
        self.db_session.notify(f'Initiating live test - hope the core is stable 🤞')
        

    def run(self):
        """Fire and forget function to start the live loop and keep it running in a seperate thread."""
        if self.running:
            raise RuntimeError('Already running')
        self.will_stop = False
        self.running = True
        self.thread = threading.Thread(target=self.__run, name=f'LL:{self.db_symbol.base}@{self.market.name}')
        self.thread.start()

    def __run(self):
        logger.info(f'Starting live loop for {self.symbol} on {self.market.name} with freq {self.freq.replace(" ", "").upper()}')
        last_order = None
        while not self.should_stop() and self.wait_next_candle():
            self.handle_manual_overrides()

            last_klines = self.market.get_last_klines(self.symbol, self.freq)
            raw_dataset = OHLCVDataset(last_klines)
            strategy_dataset = self.strategy(raw_dataset)

            self.last_kline_dt = strategy_dataset.index[-1].to_pydatetime()
            last_kline = strategy_dataset.iloc[-1]
            positive_buy_signal = last_kline['buy']
            positive_sell_signal = last_kline['sell']

            self.testman.update(kline={'time': self.last_kline_dt, **last_kline.to_dict()})

            if positive_buy_signal:
                db_signal = add_signal(
                    session=self.db_session,
                    timestamp=self.last_kline_dt, 
                    side='buy', 
                    price=last_kline['close'], 
                    rawrow=last_kline.to_dict()
                )
                if not self.testman.bought:
                    last_order = self.market.place_market_order(self.symbol, 'buy', funds=self.testman.capital)
                    db_order = add_order(
                        signal=db_signal,
                        side='buy',
                        price=last_order.price,
                        quantity=last_order.deal_funds,
                        size=last_order.deal_size,
                        order_type=last_order.type,
                        status=last_order.status,
                        timestamp=last_order.created
                    )
                    self.db_session.notify(f'[ORDER] BUY {self.db_symbol.base}@{last_kline["close"]} in {self.market} ({self.last_kline_dt.strftime("%d-%m-%Y, %H:%M:%S")} UTC)')
                else:
                    self.db_session.notify(f'[SIGNAL] BUY {self.db_symbol.base}@{last_kline["close"]} in {self.market} ({self.last_kline_dt.strftime("%d-%m-%Y, %H:%M:%S")} UTC)')
                self.testman.buy({'time': self.last_kline_dt, **last_kline.to_dict()}, sync=last_order)
            
            elif positive_sell_signal:
                db_signal = add_signal(
                    session=self.db_session,
                    timestamp=self.last_kline_dt,
                    side='sell',
                    price=last_kline['close'],
                    rawrow=last_kline.to_dict()
                )
                if self.testman.bought:
                    last_order = self.market.place_market_order(self.symbol, 'sell', quantity=self.testman.assets)
                    db_order = add_order(
                        signal=db_signal,
                        side='sell',
                        price=last_order.price,
                        quantity=last_order.deal_funds,
                        size=last_order.deal_size,
                        order_type=last_order.type,
                        status=last_order.status,
                        timestamp=last_order.created
                    )
                    self.db_session.notify(f'[ORDER] SELL {self.db_symbol.base}@{last_kline["close"]} in {self.market} ({self.last_kline_dt.strftime("%d-%m-%Y, %H:%M:%S")} UTC)')
                else:
                    self.db_session.notify(f'[SIGNAL] SELL {self.db_symbol.base}@{last_kline["close"]} in {self.market} ({self.last_kline_dt.strftime("%d-%m-%Y, %H:%M:%S")} UTC)')
                self.testman.sell({'time': self.last_kline_dt, **last_kline.to_dict()}, sync=last_order)

            self.db_session.heartbeat()
            summary = self.testman.summary()
            logger.info(summary)
        self.running = False
        report = self.testman.shutdown(save=True)
        self.db_session.ended = datetime.now(tz=pytz.UTC)
        self.db_session.testman_dir = report
        self.db_session.status = 'completed'
        self.db_session.notify(f'Live loop completed, summary: {summary}')
        sql_session.commit()

    def handle_manual_overrides(self):
        """Handle manual overrides such as force buy, update capital limit etc."""
        pass

    def should_stop(self):
        """Returns whether the loop should stop or not

        Returns:
            bool: True if the loop should stop, False otherwise
        """
        before_end = True
        if self.end:
            before_end = datetime.now(tz=pytz.UTC) < self.end
        return self.will_stop or not before_end

    def wait_next_candle(self):
        """Waits until the next candle is available"""
        if not self.last_kline_dt:
            return True
        last_kline_ts = self.last_kline_dt.timestamp()
        residue = last_kline_ts + self.loop_interval_s + 5 - time.time()
        if residue > 0:
            time.sleep(residue)
        else:
            # new candle is not available yet
            time.sleep(1)
        return True

    def stop(self):
        self.will_stop = True
    
    def force_buy(self):
        pass

    def force_sell(self):
        pass

    def force_shutdown(self):
        pass

    def update_capital_limit(self):
        pass

    def update_asset_limit(self):
        pass

    def idle(self):
        """Idle indefinitely (for development purposes)"""
        while True:
            if not self.thread.is_alive():
                logger.error(f'Thread ({self.thread.name}) died, exiting')
                break
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                break


def run_livetest(symbol, market:Market, strategy:callable, freq='15 min', end:datetime=None):
    db_market = get_db_market(market.name)
    db_symbol = add_db_symbol(symbol, db_market)
    db_session = add_session(
        symbol=db_symbol,
        market=db_market,
        strategy=strategy.name,
        strategy_parameters=strategy.params,
        test_type='live.basic',
        freq=freq,
        planned_shutdown=end)
    symbol = symbol.upper()
    testman = TestManager(symbol=symbol, market=market, live=True, strategy=strategy) # params are optional
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
            db_signal = add_signal(
                session=db_session,
                timestamp=ds.index[-1], 
                side='buy', 
                price=kline['close'], 
                rawrow=kline.to_dict()
            )
            if not testman.bought:
                testman.buy({'time': ds.index[-1], **kline.to_dict()})
                last_order = testman.trades[-1]
                db_order = add_order(
                    signal=db_signal, 
                    side='buy', 
                    quantity=last_order.capital,
                    size=last_order.assets,
                    order_type='MARKET',
                    status='FILLED',
                    timestamp=last_order.datetime
                )
        elif should_sell:
            db_signal = add_signal(
                session=db_session,
                timestamp=ds.index[-1], 
                side='sell', 
                price=kline['close'], 
                rawrow=kline.to_dict()
            )
            if not testman.bought:
                testman.sell({'time': ds.index[-1], **kline.to_dict()})
                last_order = testman.trades[-1]
                db_order = add_order(
                    signal=db_signal, 
                    side='sell', 
                    quantity=last_order.assets,
                    size=last_order.capital,
                    order_type='MARKET',
                    status='FILLED',
                    timestamp=last_order.datetime
                )
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
    db_session = add_session(
        symbol=db_symbol,
        market=db_market,
        strategy=strategy.name,
        strategy_parameters=strategy.params,
        test_type='live.sandbox',
        freq=freq,
        planned_shutdown=end)
    db_user = sql_session.query(DBUser).filter(DBUser.id == 1).first()
    add_subscription(db_user, db_session)

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

    db_session.notify(f'Initiating live test - hope the core is stable 🤞')

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
                session=db_session,
                timestamp=stg_ds.index[-1], 
                side='buy', 
                price=last_kline['close'], 
                rawrow=last_kline.to_dict()
            )
            db_session.notify(f'[SIGNAL] BUY {symbol}@{last_kline["close"]} in {market} ({stg_ds.index[-1]} UTC)')
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
                    timestamp=last_order.created
                )
                if not last_order.status in ['ACTIVE', 'FILLED']:
                    logger.error(f'Order {last_order.oid} failed to fill, status: {last_order.status}')
                db_session.notify(f'[ORDER] BUY {symbol}@{last_kline["close"]} in {market} ({stg_ds.index[-1]} UTC)')
            testman.buy({'time': stg_ds.index[-1], **last_kline.to_dict()}, sync=last_order)
        elif should_sell:
            db_signal = add_signal(
                session=db_session,
                timestamp=stg_ds.index[-1], 
                side='sell', 
                price=last_kline['close'], 
                rawrow=last_kline.to_dict()
            )
            db_session.notify(f'[SIGNAL] SELL {symbol}@{last_kline["close"]} in {market} ({stg_ds.index[-1]} UTC)')
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
                    timestamp=last_order.created
                )
                if not last_order.status in ['ACTIVE', 'FILLED']:
                    logger.error(f'Order {last_order.oid} failed to fill, status: {last_order.status}')
                db_session.notify(f'[ORDER] SELL {symbol}@{last_kline["close"]} in {market} ({stg_ds.index[-1]} UTC)')
            testman.sell({'time': stg_ds.index[-1], **last_kline.to_dict()}, sync=last_order)
        print(testman.summary())
        db_session.heartbeat()
        last_kline_ts = stg_ds.index[-1].timestamp()
    testman_dir = testman.shutdown(save=True)
    # set session end time and save
    db_session.ended = datetime.now(tz=pytz.UTC)
    db_session.testman_dir = testman_dir
    sql_session.commit()


def sample_livetest():
    strg = get_strategy('v1')()
    run_livetest('TARA-USDT', 'MEXC', strg)

def sample_livetest_sandbox():
    conf = json.load(open('api.json'))['BINANCE-TESTNET']
    strg = get_strategy('v1')()
    run_livetest_in_sandbox('DOGE-USDT', get_market('BINANCE', conf), strg, freq='3 min')

if __name__ == '__main__':
    sample_livetest_sandbox()
