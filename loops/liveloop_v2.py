import threading
from typing import Optional
from django.utils import timezone
from loops.errors import AlreadyRunningError, CannotFetchCandles, NoEquityError
from markets.errors import KlineFetchFailed
from models import OHLCVDataset, interval_to_minutes
from quantapi.models import Session
from strategy import get_strategy
from loops.config import MAX_SUBSEQUENT_SKIPPED_CANDLES, RETRY_FAILED_CANDLE_AGAIN
class LiveLoop:
    def __init__(self, session: Session):
        self.symbol = session.symbol
        self.account = session.account
        self.session = session
        self.group = session.group
        self.interface = self.account.get_interface()
        self.strategy = get_strategy(session.strategy.code)()
        self.thread = None
        self.running = False
        self.will_stop = False
        self.last_kline = None
        self.last_100_klines = None
        self.interval = interval_to_minutes(session.freq) * 60
    def precheck(self):
        '''Internal sanity check done before running the loop.'''
        if self.running and self.thread:
            raise AlreadyRunningError()
        self.account.refresh(self.interface)
        self.session.refresh(self.interface)
    def snapshot(self):
        '''Prepare a recent snapshot of candles to be used by the strategy.'''
        market_last_klines = self.interface.get_last_klines(self.symbol, self.session.freq, limit=100)
        if not market_last_klines:
            raise CannotFetchCandles()
        self.last_100_klines = OHLCVDataset(market_last_klines)
        self.last_kline = {**dict(self.last_100_klines.iloc[-1].to_dict()), 'time': self.last_100_klines.index[-1].to_pydatetime()}
        self.session.last_kline_timestamp = self.last_kline['time']
        self.session.save()
    def run(self):
        self.precheck()
        self.snapshot()
        source_mapping = {
            Session.CandleSource.REST: self.run_polling,
            Session.CandleSource.WEBSOCKET: self.run_websocket,
            Session.CandleSource.TRADE: self.run_match_engine
        }
        runner = source_mapping[self.session.candle_source]          # type: ignore
        name = f'LiveLoop-{self.session.candle_source}:{self.symbol.base}:{self.session.freq}@{self.interface.name}'
        self.thread = threading.Thread(target=runner, name=name)
        self.thread.start()
        self.session.thread_id = self.thread.ident
        self.session.last_heartbeat = timezone.now()
        self.session.last_kline_timestamp = self.last_kline['time']  # type: ignore
        self.session.last_price = self.last_kline['close']           # type: ignore
        self.session.save()
    def run_polling(self):
        skipped_subsequently = 0
        while not self.will_stop:
            for _ in range(RETRY_FAILED_CANDLE_AGAIN):
                try:
                    last_klines = self.interface.get_last_klines(self.symbol, self.session.freq)
                    break
                except KlineFetchFailed:
                    continue
            if not last_klines:
                skipped_subsequently += 1
                if skipped_subsequently > MAX_SUBSEQUENT_SKIPPED_CANDLES:
                    self.crash('Too many subsequent skipped candles.')
                    break
                continue
            skipped_subsequently = 0
            last_klines_df = OHLCVDataset(last_klines)
            self.last_kline = {**dict(last_klines_df.iloc[-1].to_dict()), 'time': last_klines_df.index[-1].to_pydatetime()}
            self.on_candle()
        self.exit()
    def run_websocket(self):
        pass
    def run_match_engine(self):
        pass
    def on_candle(self):
        pass
    def crash(self, msg:Optional[str]=None, exc:Optional[Exception]=None):
        pass
    def exit(self):
        self.running = False
        self.will_stop = True
        self.thread = None
        self.session.thread_id = None
        self.session.ended = timezone.now()
        self.session.save()
    def stop(self, blocking=False):
        if not self.thread or not self.running:
            return
        self.will_stop = True
        self.interface.stop_websocket_stream = True
        if blocking:
            self.thread.join()
