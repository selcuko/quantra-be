from datetime import datetime
import json
from unittest import mock
from django.test import TestCase
from unittest.mock import patch, MagicMock

from markets import get_market
from markets.binance import BinanceMarket
from quantapi.models import Market, MarketSymbol
from binance.client import Client
import logger

class BinanceTests(TestCase):
    @patch.object(BinanceMarket, 'get_account', return_value={})
    @patch.object(BinanceMarket, 'get_symbols', return_value={})
    def setUp(self, mock_get_account, mock_get_symbols):
        # disable logging for tests
        logger.logger.setLevel('CRITICAL')
        self.market = Market.objects.create(
            exchange_name='BINANCE',
            friendly_name='Binance Testing Interface',
            config_enc='fake-config-hash'
        )
        self.interface = BinanceMarket({
            'API_KEY': 'test-api-key',
            'API_SECRET': 'test-api-secret',
        }, self.market)
        self.assertEqual(MarketSymbol.objects.all().count(), 0)
        self.interface.assets = {
            'USDT': 200,
            'BTC': 0.1,
            'ETH': 0.0,
        }
        self.interface.symbols = {
            'BTC-USDT': MarketSymbol.objects.create(market=self.market, base='BTC', quote='USDT'),
            'ETH-USDT': MarketSymbol.objects.create(market=self.market, base='ETH', quote='USDT'),
            'BNB-USDT': MarketSymbol.objects.create(market=self.market, base='BNB', quote='USDT'),
        }


    @patch.object(Client, 'get_account')
    def test_get_account(self, mock_get_account):
        self.assertEqual(self.interface.spot_trading_enabled, False)
        self.assertEqual(self.interface.capital, 0)

        mock_get_account.return_value = {
            'canTrade': True,
            'permissions': ['SPOT'],
            'balances': [
                {'asset': 'USDT', 'free': 100.0, 'locked': 0.0},
                {'asset': 'BTC', 'free': 0.1, 'locked': 0.0},
                {'asset': 'ETH', 'free': 0.0, 'locked': 0.0},
                {'asset': 'BNB', 'free': 0.0, 'locked': 0.0},
            ]
        }

        self.interface.get_account()

        self.assertEqual(self.interface.spot_trading_enabled, True)
        self.assertEqual(self.interface.capital, 100.0)
        self.assertEqual(self.interface.assets.get('BTC'), 0.1)
        self.assertEqual(self.interface.assets.get('ETH'), 0.0)


    @patch.object(Client, 'get_exchange_info')
    def test_get_symbols(self, mock_get_exchange_info):
        MarketSymbol.objects.all().delete()
        mock_get_exchange_info.return_value = {
            'symbols': [
                {'symbol': 'BTCUSDT', 'quoteAsset': 'USDT', 'baseAsset': 'BTC', 'baseAssetPrecision': 6, 'quotePrecision': 4, 'isSpotTradingAllowed': True},
                {'symbol': 'ETHUSDT', 'quoteAsset': 'USDT', 'baseAsset': 'ETH', 'baseAssetPrecision': 1, 'quotePrecision': 3, 'isSpotTradingAllowed': False},
                {'symbol': 'BNBUSDT', 'quoteAsset': 'USDT', 'baseAsset': 'BNB', 'baseAssetPrecision': 2, 'quotePrecision': 5, 'isSpotTradingAllowed': True},
            ]
        }

        self.interface.get_symbols()

        self.assertIn('BTC-USDT', self.interface.symbols)
        self.assertIn('ETH-USDT', self.interface.symbols)
        self.assertIn('BNB-USDT', self.interface.symbols)
        btc = MarketSymbol.objects.get(base='BTC', market=self.market)
        self.assertEqual(btc.quote, 'USDT')
        self.assertEqual(btc.base_precision, 6)
        self.assertEqual(btc.quote_precision, 4)
        self.assertEqual(btc.spot_trading_enabled, True)

        eth = MarketSymbol.objects.get(base='ETH', market=self.market)
        self.assertEqual(eth.spot_trading_enabled, False)


    @patch.object(Client, 'get_all_tickers')
    def test_get_prices(self, mock_get_all_tickers):
        mock_get_all_tickers.return_value = [
            {'symbol': 'BTCUSDT', 'price': '50000.00'},
            {'symbol': 'ETHUSDT', 'price': '3000.00'},
            {'symbol': 'BNBUSDT', 'price': '500.00'},
        ]

        self.interface.assets['BTC'] = 0.1
        equity = self.interface.get_equity()
        self.assertEqual(equity, 5000.0)

        prices = json.loads(self.interface.market.prices or '{}')
        self.assertEqual(prices.get('BTC-USDT'), 50000.0)
        self.assertEqual(prices.get('ETH-USDT'), 3000.0)
        self.assertEqual(prices.get('BNB-USDT'), 500.0)


    @patch.object(Client, 'order_market')
    def test_place_market_order(self, mock_order_market):
        mock_order_market.return_value = {
            'symbol': 'BTCUSDT',
            'orderId': 123456789,
            'orderListId': -1,
            'clientOrderId': 'web_123456789',
            'transactTime': 1620000000000,
            'price': '150.0',
            'origQty': '0.1',
            'executedQty': '0.1',
            'type': 'MARKET',
            'status': 'FILLED',
            'cummulativeQuoteQty': '100.0',
            'side': 'BUY',
        }
        order = self.interface.place_market_order('BTC-USDT', 'buy', 100, validate=False)
        called_params = mock_order_market.call_args.kwargs
        self.assertEqual(called_params.get('symbol'), 'BTCUSDT')
        self.assertEqual(called_params.get('side'), 'buy')
        self.assertEqual(called_params.get('quoteOrderQty'), 100)

        self.assertEqual(order.deal_funds, 100)
        self.assertEqual(order.price, 150)
        self.assertEqual(order.deal_size, 0.1)
        self.assertEqual(order.status, 'FILLED')
        self.assertEqual(order.oid, 123456789)

