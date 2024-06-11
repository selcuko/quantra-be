from django.test import TestCase
from quantapi.models import Market, MarketAccount, MarketCredentials


class QuantTestCase(TestCase):
    def setup_market(self, exchange='TEST-EXCHANGE'):
        self.market = Market.objects.create(exchange_name=exchange)
        return self.market

    def setup_account(self, market=None):
        if not market:
            try:
                market = self.market
            except AttributeError:
                market = self.setup_market()
        self.credentials = MarketCredentials.objects.create(
            owner='John Nash',
            market=market,
            internal=True,
        )
        self.account = MarketAccount.objects.get(market=market, credentials=self.credentials)
        return self.account

