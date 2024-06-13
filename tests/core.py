from django.test import TestCase
from quantapi.models import Market, MarketAccount, MarketCredentials, MarketSymbol


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

    def setup_symbol(self, name):
        if not self.market:
            raise AttributeError('Run setup_market() first.')
        return MarketSymbol.objects.create(
            name=name,
            base=name.split('-')[0],
            quote=name.split('-')[1],
            market=self.market,
            spot_trading_enabled=True,
        )

    def setup_symbols(self, names=['BTC-USDT', 'ETH-USDT']):
        return {name: self.setup_symbol(name) for name in names}

