from unittest import mock

from markets.kucoin import KucoinMarket
from tests.core import QuantTestCase
from tests.markets.mocks import mock_get_account, mock_get_symbols


class KucoinMarketTests(QuantTestCase):
    FAKE_CONFIG = {
        'API_KEY': 'FAKE_KEY',
        'API_SECRET': 'FAKE_SECRET',
    }

    def setUp(self):
        self.setup_market('KUCOIN')
        self.setup_account()

    @mock.patch.object(KucoinMarket, 'get_symbols', mock_get_symbols)
    @mock.patch.object(KucoinMarket, 'get_account', mock_get_account)
    def test_market_attributes_are_initialized(self):
        interface = KucoinMarket(self.FAKE_CONFIG, self.account)
        self.assertEqual(interface.name, 'KuCoin')
        self.assertEqual(interface.account, self.account)
        self.assertEqual(interface.market, self.market)
        self.assertEqual(str(interface), 'KuCoin Interface <John Nash>')
        self.assertEqual(interface.json(), {
            'name': 'KuCoin',
            'owner': 'John Nash',
            'exchange': 'KUCOIN',
        })
