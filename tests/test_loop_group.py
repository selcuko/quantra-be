from datetime import datetime
from unittest import mock

import pytz
from django.test import TestCase

from logger import logger
from loopgroup import LoopGroup
from quantapi.models import (Market, MarketAccount, MarketCredentials,
                             MarketSymbol, SessionGroup, Strategy)
from tests.mocks import MockCache, mock_get_interface, mock_get_strategy


class LoopGroupTests(TestCase):
    def setUp(self):
        logger.disabled = True
        self.market = Market.objects.create(exchange_name='OKX')
        self.symbol = MarketSymbol.objects.create(
            market=self.market,
            name='BTC-USDT',
            base='BTC',
            quote='USDT',
        )
        self.strategy = Strategy.objects.create(
            name='Test Strategy',
            technical_name='Technical Test Strategy',
            code='tts',
            version='2.1a',
        )
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

    @mock.patch('loopgroup.cache', MockCache)
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

    @mock.patch('loopgroup.cache', MockCache)
    @mock.patch('loopgroup.get_strategy', mock_get_strategy)
    @mock.patch.object(MarketAccount, 'get_interface', mock_get_interface)
    def test_loop_precheck_passes(self):
        loop = LoopGroup(self.group)
        ok = loop.precheck()
        self.assertEqual(ok, True)
        self.assertEqual(loop.precheck_passed, True)
        self.assertIsNotNone(loop.strategy)
        self.assertIsNotNone(loop.interface)

    @mock.patch('loopgroup.cache', MockCache)
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

    @mock.patch('loopgroup.cache', MockCache)
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
