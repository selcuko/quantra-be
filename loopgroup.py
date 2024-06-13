

import json
import time
from threading import Thread
from typing import Optional

import pandas as pd
import django
from django.core.cache import cache
from django.utils import timezone
django.setup()

from logger import logger
from markets.errors import MarketAPIUnavailable, OrderPostProcessingError
from models import OHLCVDataset, interval_to_minutes
from order import GroupOrderManager, OrderManager
from quantapi.models import GroupOrder, Issue, Order, Session, SessionGroup, Signal
from quantapi.models import Strategy as StrategyModel
from strategy import Strategy, get_strategy

MINIMUM_INITIAL_CAPITAL = 0
MINIMUM_BUY_AMOUNT = 5
FAILED_KLINE_LIMIT = 3    # limit before alerting everyone


class PrecheckFailed(Exception):
    pass


class PrecheckNotCalled(Exception):
    pass


class CriticalFailure(Exception):
    pass


def ensure_precheck(func):
    def wrapper(self, *args, **kwargs):
        if not self.precheck_passed or not self.interface:
            raise PrecheckNotCalled('Precheck must pass before running this function.')
        return func(self, *args, **kwargs)
    return wrapper


class LoopGroup:
    def __init__(
            self,
            group: SessionGroup,
            freq: Optional[str]=None,
            strategy: Optional[Strategy]=None,
    ) -> None:
        self.group = group
        self.symbol = group.symbol
        self.market = group.market
        self.strategy = strategy
        self.freq = freq or group.freq
        self.loop_interval_s = interval_to_minutes(self.freq) * 60

        self.thread: Optional[Thread] = None
        self.died = []
        self.health = 'alive'
        self.will_stop = False
        self.precheck_passed = False
        self.failed_kline_count = 0   # klines failed to fetch in a row
        self.last_kline_dt = timezone.now()
        self.last_kline = None

        self.sessions: list[Session] = list(group.sessions.all())
        self.accounts = [s.account for s in self.sessions]

        # XXX: remove "if a" part once session.account is not nullable
        # XXX: also get_interface() is not async
        self.interfaces = {}
        for a in self.accounts:
            try:
                self.interfaces[a] = a.get_interface()
            except MarketAPIUnavailable as exc:
                issue = Issue.from_exception(exc)
                issue.object = a
                issue.level = Issue.Level.CRITICAL
                issue.save()
                logger.critical(
                    f'Error while getting interface for account {a.pk}.',
                    extra={'group': self, 'subject': 'Error while getting interface.', 'account': a},
                    exc_info=True
                )
        self.interface = group.interface.get_interface() if group.interface else None
        cache.set(f'sessiongroup_{group.pk}', self)
        logger.info(
            f'LoopGroup initialized with {len(self.sessions)} sessions.',
            extra={'group': self, 'subject': 'LoopGroup initialized.'}
        )


    def is_alive(self):
        return self.health == 'alive' and self.thread and self.thread.is_alive()


    def precheck(self):
        # assign strategy
        if not self.strategy:
            try:
                self.strategy = get_strategy(self.group.strategy.code)()
            except StrategyModel.DoesNotExist:
                raise PrecheckFailed(f'Strategy object with code={self.group.strategy.code} not found.')

        # assert there are accounts to work with
        if len(self.accounts) == 0:
            raise PrecheckFailed('No accounts found in group.')

        if len(self.interfaces) == 0:
            raise PrecheckFailed('No interfaces found in group.')

        # assert capital assignment is good enough
        for session in self.sessions:
            if session.capital < MINIMUM_INITIAL_CAPITAL:
                raise PrecheckFailed(f'Capital (${session.capital}) of session (id={session.pk}) is less than minimum initial capital of ${MINIMUM_INITIAL_CAPITAL}.')

        # the interface to fetch data from
        if not self.interface:
            account = self.accounts[0]
            self.interface = self.interfaces[account]
            self.group.interface = account
            self.group.save()
        self.precheck_passed = True
        logger.info(
            f'LoopGroup precheck passed.',
            extra={'group': self, 'subject': 'LoopGroup precheck passed.'}
        )
        return True


    @ensure_precheck
    def prepare_kline_snapshot(self):
        assert self.interface is not None
        last_klines = self.interface.get_last_klines(self.symbol.name, self.freq, limit=100)

        # kline sanity check
        if not last_klines:
            if self.failed_kline_count < FAILED_KLINE_LIMIT:
                self.failed_kline_count += 1
                if self.failed_kline_count == 0:
                    logger.error(
                        f'Failed to fetch candles from {self.market.exchange_name} REST API.',
                        extra={'group': self, 'subject': 'SessionGroup cannot fetch candles.'}
                    )
                    return False
            else:
                logger.critical(
                    f'Terminating SessionGroup after candle fetch attempts failed {self.failed_kline_count} times.',
                    extra={'subject': 'Unplanned termination of SessionGroup.'}
                )
                self.fail()

        last_klines_ds = OHLCVDataset(last_klines)
        self.last_kline_dt = last_klines_ds.index[-1].to_pydatetime()
        self.last_kline = last_klines_ds.iloc[-1].to_dict()
        self.last_100_klines = last_klines_ds
        return True


    def fail(self, exc:Optional[Exception]=None):
        now = timezone.now()
        self.group.status = SessionGroup.Status.ERROR
        self.group.stopped_at = now
        self.group.save()
        for session in self.sessions:
            session.status = Session.Status.ERROR
            session.ended = now
        Session.objects.bulk_update(self.sessions, fields=['status', 'ended'])
        raise CriticalFailure('This SessionGroup encountered a fatal error and cannot continue running.')


    def stop(self):
        self.will_stop = True
        self.group.status = SessionGroup.Status.PAUSED
        self.group.save()
        for session in self.sessions:
            session.status = Session.Status.PAUSED
        Session.objects.bulk_update(self.sessions, fields=['status'])
        logger.info(
            f'LoopGroup stopped.',
            extra={'group': self, 'subject': 'LoopGroup stopped.'}
        )
        return


    def run(self, threaded=True, **kwargs):
        logger.info(
            f'LoopGroup started with threaded={threaded}.',
            extra={'group': self, 'subject': 'LoopGroup started.'}
        )
        if threaded:
            Thread(target=self.run, name='LoopGroupPrepper', kwargs={'threaded':False, **kwargs}, daemon=True).start()
            return
        self.will_stop = False

        try:
            self.precheck()
        except PrecheckFailed:
            logger.critical(
                f'This SessionGroup encountered a fatal error in precheck and could not start.',
                extra={'group': self, 'subject': 'SessionGroup precheck failed.'},
                exc_info=True
            )
            self.fail()
        
        while not self.prepare_kline_snapshot():
            self.wait_next_candle()

        source = kwargs.get('source', self.group.source).lower()
        if source == 'trade':
            thread_name = f'LoopGroup-MatchEngine-{self.symbol.name}'
            self.thread = Thread(target=self.run_match_engine, name=thread_name, daemon=True)
        else:
            raise ValueError(f'Invalid source for LoopGroup (source={source}).')
        self.thread.start()
        logger.info(
            f'LoopGroup started with {source} as source.',
            extra={'group': self, 'subject': 'LoopGroup started.'}
        )
        self.group.thread_id = self.thread.ident
        self.group.last_price = self.last_kline['close'] if self.last_kline else None
        self.group.last_kline_dt = self.last_kline_dt
        self.group.status = SessionGroup.Status.ONGOING
        self.group.started_at = timezone.now()
        self.group.save()
        
        for session in self.sessions:
            session.started = timezone.now()
            session.status = Session.Status.ONGOING
        Session.objects.bulk_update(self.sessions, fields=['status', 'started'])


    def run_match_engine(self):
        try:
            assert self.interface is not None
            self.interface.init_match_engine(
                self.symbol.name,
                self.freq,
                self.on_candle,
                self
            )
        except:
            logger.critical(
                f'Error while initializing match engine for LoopGroup.',
                extra={'group': self, 'subject': 'SessionGroup failed to initialize'},
                exc_info=True
            )
            self.fail()
        self.group.status = SessionGroup.Status.COMPLETED
        self.group.save()
        logger.info(
            f'LoopGroup completed.',
            extra={'group': self, 'subject': 'LoopGroup completed.'}
        )
        return


    def wait_next_candle(self):
        if not self.last_kline_dt:
            started = timezone.now().timestamp()
            end = started + self.loop_interval_s
            while timezone.now().timestamp() < end and not self.will_stop:
                time.sleep(1)
        else:
            last_kline_ts:float = self.last_kline_dt.timestamp()
            next_kline_ts = last_kline_ts + self.loop_interval_s + 5
            now_ts = timezone.now().timestamp()
            delta = next_kline_ts - now_ts
            if delta < 0:
                logger.warning(
                    f'LoopGroup is behind schedule by {abs(delta)} seconds.',
                    extra={'group': self, 'subject': 'LoopGroup is behind schedule.'}
                )

            while delta > 0 and not self.will_stop:
                time.sleep(1)
                delta -= 1

        return


    def should_stop(self):
        return self.will_stop


    def on_candle(self, candle):
        logger.info(
            f'LoopGroup received a candle event.',
            extra={'group': self, 'subject': 'LoopGroup received event.'}
        )
        if self.group.status != SessionGroup.Status.ONGOING:
            logger.warning(
                f'LoopGroup is not running, but received a candle event.',
                extra={'group': self, 'subject': 'LoopGroup received event while not running.'}
            )
            return
        assert self.interface is not None
        self.interface.cache_to_db()

        self.last_kline_dt = candle['time']

        if self.group.last_kline_dt and self.group.last_kline_dt >= self.last_kline_dt:
            logger.warning(
                f'LoopGroup received an outdated candle event. Last kline time: {self.group.last_kline_dt}, received kline time: {self.last_kline_dt}.',
                extra={'group': self, 'subject': 'LoopGroup received outdated event.'}
            )
            return

        if self.last_100_klines is None:
            logger.error(
                f'LoopGroup received a candle event without a proper kline snapshot.',
                extra={
                    'group': self, 
                    'subject': 'LoopGroup received event without kline snapshot.'
                }
            )
            self.failed_kline_count += 1
            return
        assert self.strategy is not None
        candle_ds = OHLCVDataset([candle])
        self.last_100_klines = pd.concat([self.last_100_klines, candle_ds])
        self.last_100_klines = self.last_100_klines.iloc[-100:]
        dataset = OHLCVDataset(self.last_100_klines, pass_thru=True)
        processed_ds = self.strategy(dataset)
        self.last_kline = {'time': self.last_kline_dt.timestamp(), **processed_ds.iloc[-1].to_dict()}

        buy_signal  = self.last_kline['buy']
        sell_signal = self.last_kline['sell']

        if buy_signal:
            self.buy(self.last_kline)

        elif sell_signal:
            self.sell(self.last_kline)

        self.group.last_kline_dt = self.last_kline_dt
        self.group.save()
        return True


    def can_buy(self, session:Session):
        assert session.account is not None
        return (session.capital or 0) > MINIMUM_BUY_AMOUNT and self.group.buy_enabled


    def can_sell(self, session:Session):
        assert session.account is not None
        return (session.assets or 0) > 0 and self.group.sell_enabled


    def buy_for_session(self, session: Session, amount:Optional[float]=None):
        if not self.can_buy(session):
            return

        assert session.account is not None
        interface = self.interfaces[session.account]
        manager = OrderManager(interface, session)

        try:
            order = manager.place(
                symbol=self.symbol,
                side='buy',
                deal_funds=amount or session.capital,
            )
        except OrderPostProcessingError:
            logger.critical(
                f'Order post process failed for session {session.pk} within SessionGroup Order might or might not be placed.',
                extra={'group': self, 'subject': 'Order post process failed.', 'type': 'ORDER'},
                exc_info=True
            )
            return
        except:
            logger.critical(
                f'Unhandled error while placing BUY order for session {session.pk}.',
                extra={'group': self, 'subject': 'Unhandled error prevented buy order', 'type': 'ORDER'},
                exc_info=True
            )
            return

        if order.status == Order.Status.INSUFFICIENT_BALANCE:
            interface.get_account()
            old_capital = session.capital
            session.capital = max(interface.capital, 0)
            session.save()
            logger.warning(
                f'Insufficient balance for session {session.pk} to place order. Capital reduced from ${old_capital} to ${session.capital}.',
                extra={'group': self, 'subject': 'Insufficient balance for buy order.', 'type': 'ORDER'}
            )
            return self.buy_for_session(session)

        elif order.status == Order.Status.REJECTED:
            logger.critical(
                f'Order was rejected for session {session.pk} (OrderID={order.pk}).',
                extra={'group': self, 'subject': 'Order was rejected.', 'type': 'ORDER', 'order': order}
            )
            return
        elif order.status == Order.Status.FILLED:
            assert order.deal_funds is not None
            assert order.deal_size is not None
            session.capital -= order.deal_funds
            session.assets += order.deal_size
            session.save()
            logger.info(
                f'Order was filled for session {session.pk} (OrderID={order.pk}).',
                extra={'group': self, 'subject': 'Order was filled.', 'type': 'ORDER', 'order': order}
            )
        return order


    def buy(self, last_kline:dict):
        signal = Signal.objects.create(
            group=self.group,
            timestamp=self.last_kline_dt,
            side=Signal.Side.BUY,
            price=last_kline['close'],
            raw=json.dumps(last_kline)
        )
        group_order_manager = GroupOrderManager(self.group)
        group_order = group_order_manager.place('buy')
        if not group_order:
            return
        group_order.signal = signal
        group_order.save()
        return group_order


    def buy_manual(self, pct:int):
        group_order = GroupOrder.objects.create(
            group=self.group,
            side=Order.Side.BUY,
            status=GroupOrder.Status.PENDING
        )
        for session in self.sessions:
            if not self.can_buy(session):
                continue
            amount = session.capital * pct / 100
            order = self.buy_for_session(session, amount)
            if not order:
                continue
            group_order.deal_funds += order.deal_funds
            group_order.deal_size += order.deal_size
        group_order.save()
        return group_order


    def sell_for_session(self, session: Session, amount:Optional[float]=None):
        if not self.can_sell(session):
            return

        assert session.account is not None
        interface = self.interfaces[session.account]
        manager = OrderManager(interface, session)

        try:
            order = manager.place(
                symbol=self.symbol,
                side='sell',
                deal_size=amount or session.assets,
            )
        except OrderPostProcessingError:
            logger.critical(
                f'Order post process failed for session {session.pk} within SessionGroup Order might or might not be placed.',
                extra={'group': self, 'subject': 'Order post process failed.', 'type': 'ORDER'},
                exc_info=True
            )
            return
        except:
            logger.critical(
                f'Unhandled error while placing SELL order for session {session.pk}.',
                extra={'group': self, 'subject': 'Unhandled error prevented sell order', 'type': 'ORDER'},
                exc_info=True
            )
            return

        if order.status == Order.Status.REJECTED:
            logger.critical(
                f'Order was rejected for session {session.pk} (OrderID={order.pk}).',
                extra={'group': self, 'subject': 'Order was rejected.', 'type': 'ORDER', 'order': order}
            )
            return
        elif order.status == Order.Status.FILLED:
            assert order.deal_funds is not None
            assert order.deal_size is not None
            session.capital += order.deal_funds
            session.assets -= order.deal_size
            session.save()
            logger.info(
                f'Order was filled for session {session.pk} (OrderID={order.pk}).',
                extra={'group': self, 'subject': 'Order was filled.', 'type': 'ORDER', 'order': order}
            )
        return order


    def sell(self, last_kline:dict):
        signal = Signal.objects.create(
            group=self.group,
            timestamp=self.last_kline_dt,
            side=Signal.Side.SELL,
            price=last_kline['close'],
            raw=json.dumps(last_kline)
        )
        group_order_manager = GroupOrderManager(self.group)
        group_order = group_order_manager.place('sell')
        if not group_order:
            return
        group_order.signal = signal
        group_order.save()
        return group_order


if __name__ == '__main__':
    logger.info(
        'LoopGroup started as main.',
        extra={'subject': 'LoopGroup started as main.'}
    )
    group = SessionGroup.objects.get(id=10)
    if not group:
        print('No SessionGroup found.')
        exit(1)
    loop = LoopGroup(group, freq='1 min')
    loop.buy({'close': 100})

    while True:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            loop.will_stop = True
            break
    print('Exiting.')

