from datetime import datetime
from unittest import mock

import pytz

from markets.binance import BinanceMarket
from quantapi.models import Order
from tests.core import QuantTestCase
from tests.markets.mocks import mock_get_account, mock_get_symbols


class BinanceMarketTests(QuantTestCase):
    FAKE_CONFIG = {
        'API_KEY': 'FAKE_KEY',
        'API_SECRET': 'FAKE_SECRET',
    }

    @mock.patch.object(BinanceMarket, 'get_symbols', mock_get_symbols)
    @mock.patch.object(BinanceMarket, 'get_account', mock_get_account)
    def setUp(self):
        self.setup_market('BINANCE')
        self.setup_symbol('BTC-USDT')
        self.setup_account()
        self.interface = BinanceMarket(self.FAKE_CONFIG, self.account)

    @mock.patch.object(BinanceMarket, 'get_symbols', mock_get_symbols)
    @mock.patch.object(BinanceMarket, 'get_account', mock_get_account)
    @mock.patch('markets.binance.Client', autospec=True)
    def test_market_attributes_are_initialized(self, mock_client):
        interface = BinanceMarket(self.FAKE_CONFIG, self.account)
        self.assertEqual(interface.name, 'Binance')
        self.assertEqual(interface.account, self.account)
        self.assertEqual(interface.market, self.market)
        self.assertEqual(str(interface), 'Binance Interface <John Nash>')
        self.assertEqual(interface.json(), {
            'name': 'Binance',
            'owner': 'John Nash',
            'exchange': 'BINANCE',
        })

    @mock.patch('markets.binance.Client.order_market')
    def test_place_market_order(self, mock_place_order):
        mock_place_order.return_value = {
            'orderId': 'oid123',
            'status': 'FILLED',
            'type': 'MARKET',
            'cummulativeQuoteQty': '99',
            'origQty': '.99',
            'origQuoteOrderQty': '100',
            'price': '100',
            'side': 'BUY',
            'transactTime': int(datetime(2020, 1, 1).timestamp() * 1000),
        }
        self.interface.symbols[self.symbol.name] = self.symbol
        order = self.interface.place_market_order(self.symbol, 'buy', funds='100')
        self.assertEqual(order.account, self.account)
        self.assertEqual(order.symbol, self.symbol)
        self.assertEqual(order.oid, 'oid123')
        self.assertEqual(order.side, Order.Side.BUY)
        self.assertEqual(order.order_type, Order.Type.MARKET)
        self.assertEqual(order.status, Order.Status.FILLED)
        self.assertEqual(order.deal_funds, 99)
        self.assertEqual(order.deal_size, 0.99)
        self.assertEqual(order.price, 100)
        self.assertEqual(order.funds, 100)
        self.assertEqual(order.market_timestamp, datetime(2020, 1, 1, tzinfo=pytz.UTC))
