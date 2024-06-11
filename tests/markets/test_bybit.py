from unittest import mock

from markets.bybit import BybitMarket
from tests.core import QuantTestCase
from tests.markets.mocks import mock_get_account, mock_get_symbols


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
