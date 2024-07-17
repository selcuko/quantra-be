


import json
from django.urls import reverse
from rest_framework.test import APIRequestFactory
from quantapi.serializers import MarketAccountSerializer, MarketSerializer
from tests.core import QuantTestCase


class SerializerTests(QuantTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.setup_market()
        self.setup_account()

    def test_market_serializer(self):
        request = self.factory.get('/markets/')
        serializer = MarketSerializer(self.market, context={'request': request})
        data = dict(serializer.data)
        self.assertEqual(data['exchange_name'], self.market.exchange_name)
        self.assertEqual(data['prices_updated'], self.market.prices_updated)

        prices = self.client.get(data['prices']).json()
        self.assertEqual(prices, { 'BTC-USDT': 50000, 'ETH-USDT': 3000 })

        account_url = self.client.get(reverse('marketaccount-detail', args=[self.account.pk])).json().get('url')
        self.assertEqual(data['accounts'], [account_url])

    def test_market_account_serializer(self):
        request = self.factory.get('/accounts/')
        serializer = MarketAccountSerializer(self.account, context={'request': request})
        data = dict(serializer.data)
        self.assertEqual(data['market']['exchange_name'], self.account.market.exchange_name)
        self.assertEqual(data['owner'], self.account.credentials.owner)
        self.assertEqual(data['capital'], self.account.capital)
        self.assertEqual(data['assets'], { 'BTC': { 'amount': 1, 'price': 50000, 'value': 50000, 'icon': None } })
