from datetime import datetime
from unittest import mock

import pytz

from logger import logger
from loopgroup import LoopGroup
from quantapi.models import (GroupOrder, MarketAccount, MarketCredentials,
                             Order, SessionGroup, Signal)
from tests.core import QuantTestCase
from tests.mocks import mock_get_interface, mock_get_strategy


class LoopGroupTests(QuantTestCase):
    def setUp(self):
        logger.disabled = True
        self.setup_market('OKX')
        self.setup_symbol('BTC-USDT')
        self.setup_strategy()
        self.credentials1 = MarketCredentials.objects.create(
            market=self.market,
            encrypted='{"fake": "credendials"}',
            owner='John Nash'
        )
        self.credentials2 = MarketCredentials.objects.create(
            market=self.market,
            encrypted='{"fake": "credendials"}',
            owner='Joe Dasher'
        )
        self.account1 = MarketAccount.objects.get(credentials=self.credentials1)
        self.account2 = MarketAccount.objects.get(credentials=self.credentials2)

        self.group = SessionGroup.objects.create(
            symbol=self.symbol,
            market=self.market,
            strategy=self.strategy,
            freq='5 min',
            status=SessionGroup.Status.PLANNED
        )
        self.session1 = self.group.add_account(self.account1)
        self.session2 = self.group.add_account(self.account2)

    @mock.patch.object(MarketAccount, 'get_interface', mock_get_interface)
    def test_loop_initiates_correctly(self):
        loop = LoopGroup(self.group)
        self.assertEqual(loop.group, self.group)
        self.assertEqual(loop.market, self.market)
        self.assertEqual(loop.symbol, self.symbol)
        self.assertEqual(loop.strategy, None)   # strategy gets set in precheck
        self.assertEqual(loop.freq, '5 min')
        self.assertEqual(loop.accounts, [self.account1, self.account2])
        self.assertEqual(loop.sessions, [self.session1, self.session2])
        self.assertEqual(loop.thread, None)
        self.assertEqual(loop.will_stop, False)

    @mock.patch('loopgroup.get_strategy', mock_get_strategy)
    @mock.patch.object(MarketAccount, 'get_interface', mock_get_interface)
    def test_loop_precheck_passes(self):
        loop = LoopGroup(self.group)
        ok = loop.precheck()
        self.assertEqual(ok, True)
        self.assertEqual(loop.precheck_passed, True)
        self.assertIsNotNone(loop.strategy)
        self.assertIsNotNone(loop.interface)

    @mock.patch('loopgroup.get_strategy', mock_get_strategy)
    @mock.patch.object(MarketAccount, 'get_interface', mock_get_interface)
    def test_loop_run_method_runs_ok(self):
        loop = LoopGroup(self.group)

        self.assertEqual(loop.precheck_passed, False)
        self.assertEqual(loop.group.status, 'PLANNED')
        for session in loop.sessions:
            self.assertEqual(session.status, 'PLANNED')

        loop.run(threaded=False)

        self.assertEqual(loop.precheck_passed, True)
        self.assertEqual(loop.group.status, 'ONGOING')
        self.assertIsNotNone(loop.thread)
        self.assertEqual(loop.is_alive(), True)
        for session in loop.sessions:
            self.assertEqual(session.status, 'ONGOING')

        loop.stop()

    @mock.patch('loopgroup.get_strategy', mock_get_strategy)
    @mock.patch.object(MarketAccount, 'get_interface', mock_get_interface)
    def test_loop_can_handle_candle_event(self):
        loop = LoopGroup(self.group)
        loop.run(threaded=False)
        candle = {
            'time': datetime(2024, 1, 2, tzinfo=pytz.UTC),
            'close': 38000.0,
        }
        loop.on_candle(candle)
        self.assertEqual(loop.last_kline_dt, candle['time'])

    @mock.patch('loopgroup.get_strategy', mock_get_strategy)
    @mock.patch.object(MarketAccount, 'get_interface', mock_get_interface)
    def test_loop_can_handle_buy_signal(self):
        self.account1.capital = 10
        self.account1.save()
        self.session1.capital = 10
        self.session1.save()
        loop = LoopGroup(self.group)
        loop.precheck()
        loop.run(threaded=False)
        candle = {
            'time': datetime(2024, 1, 2, tzinfo=pytz.UTC).timestamp(),
            'close': 38000.0,
        }
        group_order = loop.buy(candle)
        assert group_order is not None
        self.assertEqual(group_order.status, GroupOrder.Status.FILLED)
        self.assertEqual(group_order.deal_funds, 10)
        self.assertEqual(group_order.deal_size, 0.0002)
        self.assertEqual(group_order.side, Order.Side.BUY)

        signals = Signal.objects.filter(group=self.group)
        self.assertEqual(signals.count(), 1)
        signal = signals[0]
        self.assertEqual(signal.side, Signal.Side.BUY)
        self.assertEqual(signal.price, 38000.0)

        orders = Order.objects.filter(signal=signal)
        self.assertEqual(orders.count(), 1)
        order = orders[0]
        self.assertEqual(order.account, self.account1)
        self.assertEqual(order.status, Order.Status.FILLED)
        self.assertEqual(order.signal, signal)
        self.assertEqual(order.signal.price, 38000.0)   # type: ignore
        self.assertEqual(order.side, Order.Side.BUY)
        self.assertEqual(order.deal_funds, 10)

    @mock.patch('loopgroup.get_strategy', mock_get_strategy)
    @mock.patch.object(MarketAccount, 'get_interface', mock_get_interface)
    def test_loop_can_handle_sell_signal(self):
        self.account1.assets = '{ "BTC": 0.1 }'
        self.account1.save()
        self.session1.assets = 0.1
        self.session1.save()
        loop = LoopGroup(self.group)
        loop.precheck()
        loop.run(threaded=False)
        candle = {
            'time': datetime(2024, 1, 2, tzinfo=pytz.UTC).timestamp(),
            'close': 50000.0,
        }
        group_order = loop.sell(candle)
        assert group_order is not None
        self.assertEqual(group_order.status, GroupOrder.Status.FILLED)
        self.assertEqual(group_order.deal_funds, 5000.0)
        self.assertEqual(group_order.deal_size, 0.1)
        self.assertEqual(group_order.side, Order.Side.SELL)

        signals = Signal.objects.filter(group=self.group)
        self.assertEqual(signals.count(), 1)
        signal = signals[0]
        self.assertEqual(signal.side, Signal.Side.SELL)
        self.assertEqual(signal.price, 50000.0)

        orders = Order.objects.filter(signal=signal)
        self.assertEqual(orders.count(), 1)
        order = orders[0]
        self.assertEqual(order.account, self.account1)
        self.assertEqual(order.status, Order.Status.FILLED)
        self.assertEqual(order.signal, signal)
        self.assertEqual(order.signal.price, 50000.0)   # type: ignore
        self.assertEqual(order.side, Order.Side.SELL)
        self.assertEqual(order.deal_funds, 5000.0)

    @mock.patch('loopgroup.get_strategy', mock_get_strategy)
    @mock.patch.object(MarketAccount, 'get_interface', mock_get_interface)
    def test_loop_can_stop(self):
        loop = LoopGroup(self.group)
        loop.run(threaded=False)
        self.assertEqual(loop.is_alive(), True)
        loop.stop()
        thread = loop.thread
        if thread:
            thread.join(timeout=2)
        self.assertEqual(loop.is_alive(), False)
