from datetime import datetime
from unittest import mock
from django.test import TestCase
from unittest.mock import patch, MagicMock

from markets import get_market
from quantapi.models import Market



class BinanceTests(TestCase):
    def setUp(self):
        self.market = Market.objects.create(
            exchange_name='BINANCE',
            friendly_name='Fake Binance',
            mainnet_enabled=True,
            trading_enabled=True,
            config_enc='fake_config_enc',
        )

    @patch('requests.sessions.Session.request')
    def test_place_market_order(self, mock_requests):
        mock_requests.side_effect = [
                MagicMock(
                status_code=200,
                json=lambda: {
                    'symbols': ['BTCUSDT']
                }
            ),
                MagicMock(
                status_code=200,
                json=lambda: {
                    'symbol': 'BTCUSDT',
                    'orderId': 123456789,
                    'clientOrderId': 'my_order_id',
                    'transactTime': datetime.now().timestamp(),
                    'price': '0.1',
                    'origQty': '0.1',
                    'executedQty': '0.1',
                    'cummulativeQuoteQty': '0.1',
                    'status': 'FILLED',
                    'timeInForce': 'GTC',
                    'type': 'MARKET',
                    'side': 'BUY',
                }
            )
        ]
        interface = get_market(self.market.exchange_name, {
            'API_KEY': 'fake_api_key',
            'API_SECRET': 'fake_api_secret',
        })
        interface.authenticated = True
        interface.place_market_order('BTC-USDT', 'buy', 0.1)
        mock_requests.assert_called_once_with(
            'https://api.binance.com/api/v3/order',
            headers={
                'X-MBX-APIKEY': 'fake_config_enc',
            },
            params={
                'symbol': 'BTCUSDT',
                'side': 'BUY',
                'type': 'MARKET',
                'quantity': 0.1,
            }
        )