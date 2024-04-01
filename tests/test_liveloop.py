import threading
from unittest.mock import patch
from django.test import TestCase
from django.core.cache import cache

from liveloop import LiveLoop
from markets.binance import BinanceMarket
from quantapi.models import Market, MarketSymbol, Session, Strategy
from strategy import get_strategy


class LiveLoopTests(TestCase):
    @patch.object(BinanceMarket, 'get_account', return_value={})
    @patch.object(BinanceMarket, 'get_symbols', return_value={})
    def setUp(self, mock_get_account, mock_get_symbols):
        self.strategy = get_strategy('v1')()
        self.strategy_model = Strategy.objects.get_or_create(name='v1')[0]
        self.market = Market.objects.create(
            exchange_name='BINANCE',
            friendly_name='Binance Testing Market',
            trading_enabled=True,
            mainnet_enabled=True,
            usdt=100,
        )
        self.interface = BinanceMarket(
            market=self.market,
            config = {
                'API_KEY': 'fake_key',
                'API_SECRET': 'fake_secret',
            }
        )
        self.symbol = MarketSymbol.objects.create(
            name='BTC-USDT',
            market=self.market
        )
        self.session = Session.objects.create(
            strategy=self.strategy_model,
            symbol=self.symbol,
            session_type=Session.Type.LIVE_MAINNET,
            freq='15 min',
            planned_shutdown=None,
            status=Session.Status.ONGOING,
            assets=0,
            capital=100,
            initial_assets=0,
            initial_capital=100,
            candle_source=Session.CandleSource.REST,
        )

        self.interface.capital = 100
        self.interface.symbols = { 'BTC-USDT': self.symbol }

    def tearDown(self):
        print('Tearing down LiveLoop tests.')
        self.session.status = Session.Status.TERMINATED
        self.session.save()
        liveloop = cache.get(f'session_{self.session.pk}')
        if liveloop:
            print('Stopping LiveLoop.')
            liveloop.stop()
            if (thread := self.session.thread):
                print('Joining LiveLoop thread.')
                while thread.is_alive():
                    thread.join(1)
                    print(threading.enumerate())
        super().tearDown()
    
    def stop_thread(self, session):
        ll = cache.get(f'session_{session.pk}')
        if ll:
            print('Stopping LiveLoop.')
            ll.stop()
        if (thread := session.thread):
            print('Joining LiveLoop thread.')
            while thread.is_alive():
                thread.join(1)
                print(threading.enumerate())

    @patch.object(Market, 'get_interface')
    def test_init_liveloop_with_session(self, mock_get_interface):
        mock_get_interface.return_value = self.interface
        try:
            liveloop = LiveLoop(
                symbol=self.symbol.name,
                market=self.market,
                strategy=self.strategy,
                capital_limit=100,
                asset_limit=0,
                session=self.session
            )
            self.assertEqual(liveloop.symbol, self.symbol)
            self.assertEqual(liveloop.market, self.market)
            self.assertEqual(liveloop.strategy, self.strategy)
            self.assertEqual(liveloop.capital_limit, 100)
            self.assertEqual(liveloop.asset_limit, 0)
            self.assertEqual(liveloop.session, self.session)
            self.assertEqual(liveloop.freq, '15 min')
            self.assertIsNone(liveloop.thread)
            self.assertIsNone(liveloop.last_kline)
            self.assertFalse(liveloop.running)
            self.assertFalse(liveloop.will_stop)
        except Exception as e:
            self.fail(f'Failed to initialize LiveLoop with session: {e}')

    @patch.object(Market, 'get_interface')
    def test_init_liveloop_without_session(self, mock_get_interface):
        mock_get_interface.return_value = self.interface
        try:
            liveloop = LiveLoop(
                symbol=self.symbol.name,
                market=self.market,
                strategy=self.strategy,
                capital_limit=100,
                asset_limit=0,
            )
            self.assertEqual(liveloop.symbol, self.symbol)
            self.assertEqual(liveloop.market, self.market)
            self.assertEqual(liveloop.strategy, self.strategy)
            self.assertEqual(liveloop.capital_limit, 100)
            self.assertEqual(liveloop.asset_limit, 0)
            self.assertEqual(liveloop.freq, '15 min')
            self.assertIsNotNone(liveloop.session)
            self.assertEqual(liveloop.session.symbol, self.symbol)
            self.assertIsNone(liveloop.thread)
            self.assertIsNone(liveloop.last_kline)
            self.assertFalse(liveloop.running)
            self.assertFalse(liveloop.will_stop)
        except Exception as e:
            self.fail(f'Failed to initialize LiveLoop with session: {e}')

    @patch.object(Market, 'get_interface')
    def setup_liveloop(self, mock_get_interface):
        mock_get_interface.return_value = self.interface
        liveloop = LiveLoop(
            symbol=self.symbol.name,
            market=self.market,
            strategy=self.strategy,
            capital_limit=100,
            asset_limit=0,
            session=self.session
        )
        return liveloop

    @patch.object(BinanceMarket, 'get_account', return_value={})
    @patch.object(Market, 'get_interface')
    def test_continue_liveloop_polling(self, mock_get_interface, mock_get_account):
        mock_get_interface.return_value = self.interface
        try:
            ll = self.session.resume()
        except Exception as e:
            self.fail(f'Failed to resume session: {e}')
        liveloop = cache.get(f'session_{self.session.pk}')
        self.assertIsNotNone(self.session.thread_id)
        self.assertIsNotNone(liveloop)

    @patch.object(BinanceMarket, 'get_account', return_value={})
    @patch.object(Market, 'get_interface')
    def test_continue_liveloop_websocket(self, mock_get_interface, mock_get_account):
        mock_get_interface.return_value = self.interface
        self.session.candle_source = Session.CandleSource.WEBSOCKET
        self.session.save()
        try:
            self.session.resume()
        except Exception as e:
            self.fail(f'Failed to resume session: {e}')
        self.assertIsNotNone(self.session.thread_id)
        liveloop = cache.get(f'session_{self.session.pk}')
        self.assertIsNotNone(liveloop)

    @patch.object(BinanceMarket, 'get_account', return_value={})
    @patch.object(Market, 'get_interface')
    def test_continue_liveloop_match(self, mock_get_interface, mock_get_account):
        mock_get_interface.return_value = self.interface
        self.session.candle_source = Session.CandleSource.TRADE
        self.session.save()
        self.interface.capital = 100
        self.interface.symbols = { 'BTC-USDT': self.symbol }
        try:
            self.session.resume()
        except Exception as e:
            self.fail(f'Failed to resume session: {e}')
        self.assertIsNotNone(self.session.thread_id)
        liveloop = cache.get(f'session_{self.session.pk}')
        self.assertIsNotNone(liveloop)

    @patch.object(BinanceMarket, 'get_account', return_value={})
    def test_start_liveloop_polling(self, mock_get_account):
        self.session.refresh_from_db()
        print(self.session.status)
        liveloop = self.setup_liveloop()
        try:
            liveloop.run(polling=True)
        except Exception as e:
            self.fail(f'Failed to start LiveLoop: {e}')
        print('Stopping LiveLoop.')
        self.session.refresh_from_db()
        print(self.session.status)
        self.stop_thread(self.session)

    @patch.object(BinanceMarket, 'get_account', return_value={})
    def test_start_liveloop_websocket(self, mock_get_account):
        liveloop = self.setup_liveloop()
        try:
            liveloop.run(websocket=True)
        except Exception as e:
            self.fail(f'Failed to start LiveLoop: {e}')

    @patch.object(BinanceMarket, 'get_account', return_value={})
    def test_start_liveloop_match(self, mock_get_account):
        liveloop = self.setup_liveloop()
        try:
            liveloop.run(match_engine=True)
        except Exception as e:
            self.fail(f'Failed to start LiveLoop: {e}')

    def emit_buy_signal(self):
        pass

    def emit_sell_signal(self):
        pass

    def test_liveloop_can_buy_on_signal(self):
        pass

    def test_liveloop_can_sell_on_signal(self):
        pass

    def test_liveloop_can_handle_insufficient_balance_on_buy(self):
        pass

    def test_liveloop_can_handle_insufficient_balance_on_sell(self):
        pass

    def test_liveloop_can_validate_order(self):
        pass

    def test_liveloop_failed_order(self):
        pass

