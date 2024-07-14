from datetime import datetime
from unittest import mock

import pytz

from markets.errors import RejectedOrder
from markets.gateio import GateIOMarket
from quantapi.models import Order
from tests.core import QuantTestCase
from tests.markets.mocks import mock_get_account, mock_get_symbols


class GateIOMarketTests(QuantTestCase):
    FAKE_CONFIG = {
        'API_KEY': 'FAKE_KEY',
        'API_SECRET': 'FAKE_SECRET',
    }

    @mock.patch.object(GateIOMarket, 'get_symbols', mock_get_symbols)
    @mock.patch.object(GateIOMarket, 'get_account', mock_get_account)
    def setUp(self):
        self.setup_market('GATEIO')
        self.setup_symbol('BTC-USDT')
        self.setup_account()
        self.interface = GateIOMarket(self.FAKE_CONFIG, self.account)

    @mock.patch.object(GateIOMarket, 'get_symbols', mock_get_symbols)
    @mock.patch.object(GateIOMarket, 'get_account', mock_get_account)
    def test_market_attributes_are_initialized(self):
        interface = GateIOMarket(self.FAKE_CONFIG, self.account)
        self.assertEqual(interface.name, 'Gate.io')
        self.assertEqual(interface.account, self.account)
        self.assertEqual(interface.market, self.market)
        self.assertEqual(str(interface), 'Gate.io Interface <John Nash>')
        self.assertEqual(interface.json(), {
            'name': 'Gate.io',
            'owner': 'John Nash',
            'exchange': 'GATEIO',
        })

    @mock.patch('markets.gateio.requests.Session.post')
    def test_place_market_order(self, mock_post):
        mock_post.return_value.json.return_value = {
            'id': 'oid123',
            'finish_as': 'FILLED',
            'type': 'MARKET',
            'filled_total': '99',
            'filled_amount': '.99',
            'fill_price': '100',
            'side': 'BUY',
            'create_time': str(int(datetime(2020, 1, 1).timestamp())),
            'currency_pair': 'BTC_USDT',
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

    @mock.patch('markets.gateio.requests.Session.post')
    def test_place_market_order_with_small_funds(self, mock_post):
        mock_post.return_value.json.return_value = { 'msg': 'The minimum transaction volume cannot be less tha: 5USDT' }
        self.interface.symbols[self.symbol.name] = self.symbol
        with self.assertRaises(RejectedOrder):
            self.interface.place_market_order(self.symbol, 'buy', funds='100')
