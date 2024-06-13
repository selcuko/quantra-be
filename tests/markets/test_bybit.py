from datetime import datetime, timedelta
from unittest import mock

import pytz
from django.utils import timezone

from markets.bybit import BybitMarket
from tests.core import QuantTestCase
from tests.markets.mocks import mock_get_account, mock_get_symbols
from tests.mocks import MockResponse


class BybitMarketTests(QuantTestCase):
    FAKE_CONFIG = {
        'API_KEY': 'FAKE_KEY',
        'API_SECRET': 'FAKE_SECRET',
    }

    def setUp(self):
        self.setup_market('BYBIT')
        self.setup_account()

    @mock.patch.object(BybitMarket, 'get_symbols', mock_get_symbols)
    @mock.patch.object(BybitMarket, 'get_account', mock_get_account)
    def get_interface(self):
        self.interface = BybitMarket(self.FAKE_CONFIG, self.account)
        symbols = self.setup_symbols()
        for symbol in symbols.values():
            self.interface.symbols[symbol.name] = symbol
        return self.interface

    @mock.patch.object(BybitMarket, 'get_symbols', mock_get_symbols)
    @mock.patch.object(BybitMarket, 'get_account', mock_get_account)
    def test_market_attributes_are_initialized(self):
        interface = BybitMarket(self.FAKE_CONFIG, self.account)
        self.assertEqual(interface.name, 'Bybit')
        self.assertEqual(interface.account, self.account)
        self.assertEqual(interface.market, self.market)
        self.assertEqual(str(interface), 'Bybit Interface <John Nash>')
        self.assertEqual(interface.json(), {
            'name': 'Bybit',
            'owner': 'John Nash',
            'exchange': 'BYBIT',
        })

    @mock.patch('markets.bybit.requests.Session.get')
    def test_get_symbols(self, mock_get):
        mock_get.return_value = MockResponse(body={
            'retMsg': 'OK',
            'result': {'list': [
                {'symbol': 'BTCUSDT', 'baseCoin': 'BTC', 'quoteCoin': 'USDT', 'status': 'Trading', 'lotSizeFilter': {}, 'priceFilter': {}, 'marginTrading': 'none'},
                {'symbol': 'ETHUSDT', 'baseCoin': 'ETH', 'quoteCoin': 'USDT', 'status': 'Trading', 'lotSizeFilter': {}, 'priceFilter': {}, 'marginTrading': 'none'},
            ]}
        })
        interface = self.get_interface()
        symbols = interface.get_symbols()
        self.assertEqual(len(symbols), 2)
        btc = symbols['BTC-USDT']
        self.assertEqual(btc.name, 'BTC-USDT')
        self.assertEqual(btc.base, 'BTC')
        self.assertEqual(btc.quote, 'USDT')
        self.assertEqual(btc.spot_trading_enabled, True)
        self.assertEqual(btc.margin_trading_enabled, False)
        self.assertEqual(btc.market, self.market)

    @mock.patch('markets.bybit.requests.Session.get')
    def test_get_account(self, mock_get):
        mock_get.return_value = MockResponse(body={
            'retMsg': 'OK',
            'result': { 'balance': [
                {'coin': 'BTC', 'walletBalance': 0.1},
                {'coin': 'ETH', 'walletBalance': 0.2},
                {'coin': 'USDT', 'walletBalance': 1000},
            ]}
        })
        interface = self.get_interface()
        interface.get_account()
        self.assertEqual(interface.capital, 1000)
        self.assertEqual(interface.assets['BTC'], 0.1)
        self.assertEqual(interface.assets['ETH'], 0.2)

    @mock.patch('markets.bybit.requests.Session.get')
    def test_get_current_prices(self, mock_get):
        mock_get.return_value = MockResponse(body={
            'retMsg': 'OK',
            'result': { 'list': [
                {'symbol': 'BTCUSDT', 'lastPrice': 50000},
                {'symbol': 'ETHUSDT', 'lastPrice': 3000},
            ]}
        })
        interface = self.get_interface()
        prices = interface.get_current_prices()
        self.assertEqual(prices, interface.prices)
        self.assertEqual(prices['BTC-USDT'], 50000)
        self.assertEqual(prices['ETH-USDT'], 3000)

    @mock.patch('markets.bybit.requests.Session.get')
    def test_get_klines(self, mock_get):
        mock_get.return_value = MockResponse(body={
            'retMsg': 'OK',
            'result': { 'list': [
                [1640995200000, 50000, 51000, 49000, 50000, 100, None],
                [1640995260000, 3000, 3100, 2900, 3000, 200, None],
            ]}
        })
        interface = self.get_interface()
        klines = interface.get_klines('BTC-USDT', start=datetime(2024, 1, 1), interval='1 min', limit=2)
        self.assertEqual(len(klines), 2)
        first_kline = klines[0]
        last_kline = klines[1]
        self.assertEqual(first_kline[0], datetime(2022, 1, 1, tzinfo=pytz.UTC))
        self.assertEqual(last_kline[0], datetime(2022, 1, 1, 0, 1, tzinfo=pytz.UTC))
        mock_get.assert_called_with(
            f'https://api.bybit.com/v5/market/kline?category=spot&symbol=BTCUSDT&interval=1&start=1704067200000&limit=2'
        )

    @mock.patch('markets.bybit.BybitMarket.get_klines')
    def test_get_last_klines(self, mock_get_klines):
        mock_get_klines.return_value = [
            [datetime(2024, 1, 1, tzinfo=pytz.UTC), 50000, 51000, 49000, 50000, 100, None],
            [datetime(2024, 1, 1, 0, 1, tzinfo=pytz.UTC), 3000, 3100, 2900, 3000, 200, None],
        ]
        interface = self.get_interface()
        klines = interface.get_last_klines('BTC-USDT', interval='1 min', limit=2)
        self.assertEqual(len(klines), 2)
        first_kline = klines[0]
        last_kline = klines[1]
        self.assertEqual(first_kline[0], datetime(2024, 1, 1, tzinfo=pytz.UTC))
        self.assertEqual(last_kline[0], datetime(2024, 1, 1, 0, 1, tzinfo=pytz.UTC))
        now = timezone.now().replace(second=0, microsecond=0)
        mock_get_klines.assert_called_with(
            symbol='BTC-USDT',
            interval='1 min',
            start=now - timedelta(minutes=2),
            end=now + timedelta(minutes=1),
            limit=2,
        )
