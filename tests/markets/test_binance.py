from unittest import mock

from markets.binance import BinanceMarket
from tests.core import QuantTestCase
from tests.markets.mocks import mock_get_account, mock_get_symbols


class BinanceMarketTests(QuantTestCase):
    FAKE_CONFIG = {
        'API_KEY': 'FAKE_KEY',
        'API_SECRET': 'FAKE_SECRET',
    }

    def setUp(self):
        self.setup_market('BINANCE')
        self.setup_account()

    @mock.patch.object(BinanceMarket, 'get_symbols', mock_get_symbols)
    @mock.patch.object(BinanceMarket, 'get_account', mock_get_account)
    @mock.patch('binance.client.Client', autospec=True)
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
