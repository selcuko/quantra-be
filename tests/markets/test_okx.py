from unittest import mock

from markets.okx import OKXMarket
from tests.core import QuantTestCase
from tests.markets.mocks import mock_get_account, mock_get_symbols


class MEXCMarketTests(QuantTestCase):
    FAKE_CONFIG = {
        'API_KEY': 'FAKE_KEY',
        'API_SECRET': 'FAKE_SECRET',
        'API_PASSPHRASE': 'FAKE_PASSPHRASE',
    }

    def setUp(self):
        self.setup_market('OKX')
        self.setup_account()

    @mock.patch.object(OKXMarket, 'get_symbols', mock_get_symbols)
    @mock.patch.object(OKXMarket, 'get_account', mock_get_account)
    def test_market_attributes_are_initialized(self):
        interface = OKXMarket(self.FAKE_CONFIG, self.account)
        self.assertEqual(interface.name, 'OKX')
        self.assertEqual(interface.account, self.account)
        self.assertEqual(interface.market, self.market)
        self.assertEqual(str(interface), 'OKX Interface <John Nash>')
        self.assertEqual(interface.json(), {
            'name': 'OKX',
            'owner': 'John Nash',
            'exchange': 'OKX',
        })
