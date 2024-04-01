from datetime import datetime
from django.test import TestCase

from quantapi.models import Market, MarketSymbol, Session


class IndexViewTests(TestCase):
    def setUp(self):
        self.market = Market.objects.create(
            exchange_name='BINANCE',
            trading_enabled=True,
            mainnet_enabled=True,
            config_enc='fake_config_enc',
        )
        self.symbol = MarketSymbol.objects.create(
            market=self.market,
            base='BTC',
            quote='USDT'
        )
        self.session = Session.objects.create(
            session_type='live.mainnet',
            freq='1 min',
            symbol=self.symbol,
            status='ONGOING',
            initial_capital=1000,
            initial_assets=0,
            capital=0.5,
            assets=500
        )
    
    def test_get_index(self):
        self.client.login(username='admin', password='admin', email='user@example.com')
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.symbol.base)