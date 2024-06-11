from unittest import mock

from markets.gateio import GateIOMarket
from tests.core import QuantTestCase
from tests.markets.mocks import mock_get_account, mock_get_symbols


class GateIOMarketTests(QuantTestCase):
    FAKE_CONFIG = {
        'API_KEY': 'FAKE_KEY',
        'API_SECRET': 'FAKE_SECRET',
    }

    def setUp(self):
        self.setup_market('GATEIO')
        self.setup_account()

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
