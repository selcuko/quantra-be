from unittest import mock

from markets.mexc import MEXCMarket
from tests.core import QuantTestCase
from tests.markets.mocks import mock_get_account, mock_get_symbols


class MEXCMarketTests(QuantTestCase):
    FAKE_CONFIG = {
        'API_SECRET': 'FAKE_SECRET',
        'ACCESS_KEY': 'FAKE_KEY',
    }

    def setUp(self):
        self.setup_market('MEXC')
        self.setup_account()

    @mock.patch.object(MEXCMarket, 'get_symbols', mock_get_symbols)
    @mock.patch.object(MEXCMarket, 'get_account', mock_get_account)
    def test_market_attributes_are_initialized(self):
        interface = MEXCMarket(self.FAKE_CONFIG, self.account)
        self.assertEqual(interface.name, 'MEXC')
        self.assertEqual(interface.account, self.account)
        self.assertEqual(interface.market, self.market)
        self.assertEqual(str(interface), 'MEXC Interface <John Nash>')
        self.assertEqual(interface.json(), {
            'name': 'MEXC',
            'owner': 'John Nash',
            'exchange': 'MEXC',
        })

