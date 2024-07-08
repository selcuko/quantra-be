import json
from typing import Optional
from django.test import TestCase
from quantapi.models import Market, MarketAccount, MarketCredentials, MarketSymbol, Session, Strategy
import strategy


class QuantTestCase(TestCase):
    def setup_market(self, exchange='TEST-EXCHANGE'):
        self.market = Market.objects.create(exchange_name=exchange, prices=json.dumps({
            'BTC-USDT': 50000,
            'ETH-USDT': 3000,
        }))
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
        self.account.capital = 1000
        self.account.assets = '{ "BTC": 1 }'
        self.account.save()
        return self.account

    def setup_strategy(self, name='Test Strategy', version='2.1b'):
        if hasattr(self, 'strategy'):
            return self.strategy
        self.strategy = Strategy.objects.create(
            name=name,
            technical_name='Technical Test Strategy',
            code='tts',
            version=version,
        )
        return self.strategy

    def setup_session(self, account:Optional[MarketAccount]=None):
        if not account and not hasattr(self, 'account'):
            raise AttributeError('Run setup_account() first.')
        if not account:
            account = self.account
        if not hasattr(self, 'symbol'):
            self.symbol = self.setup_symbol('BTC-USDT')
        self.session = Session.objects.create(
            account=self.account,
            symbol=self.symbol,
            status=Session.Status.ONGOING,
            initial_capital=100,
            initial_assets=0,
            capital=100,
            assets=0,
            strategy=self.setup_strategy()
        )
        return self.session

    def setup_symbol(self, name):
        if not self.market:
            raise AttributeError('Run setup_market() first.')
        self.symbol = MarketSymbol.objects.create(
            name=name,
            base=name.split('-')[0],
            quote=name.split('-')[1],
            market=self.market,
            spot_trading_enabled=True,
        )
        return self.symbol

    def setup_symbols(self, names=['BTC-USDT', 'ETH-USDT']):
        return {name: self.setup_symbol(name) for name in names}
