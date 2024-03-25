from unittest.mock import patch
from django.test import TestCase

from markets import BinanceMarket, KucoinMarket, MEXCMarket
from markets.errors import InsufficientBalance, OrderNotFilledError, OrderPlacementError
from order import OrderManager
from quantapi.models import Market, MarketSymbol, Order
from logger import logger


class OrderManagerTests(TestCase):
    @patch.object(BinanceMarket, 'get_account', return_value={})
    @patch.object(BinanceMarket, 'get_symbols', return_value={})
    @patch.object(KucoinMarket, 'get_account', return_value={})
    @patch.object(KucoinMarket, 'get_symbols', return_value={})
    @patch.object(MEXCMarket, 'get_account', return_value={})
    @patch.object(MEXCMarket, 'get_symbols', return_value={})
    def setUp(self, mock_get_account_binance, mock_get_symbols_binance, 
              mock_get_account_kucoin, mock_get_symbols_kucoin, 
              mock_get_account_mexc, mock_get_symbols_mexc):
        # disable logging for tests
        logger.setLevel('CRITICAL')
        self.market_binance = Market.objects.create(
            exchange_name='BINANCE',
            friendly_name='Binance Testing Interface',
            config_enc='fake-config-hash'
        )
        self.interface_binance = BinanceMarket({
            'API_KEY': 'test-api-key',
            'API_SECRET': 'test-api-secret',
        }, self.market_binance)

        self.market_kucoin = Market.objects.create(
            exchange_name='KUCOIN',
            friendly_name='Kucoin Testing Interface',
            config_enc='fake-config-hash'
        )
        self.interface_kucoin = KucoinMarket({
            'API_KEY': 'test-api-key',
            'API_SECRET': 'test-api-secret',
        }, self.market_kucoin)

        self.market_mexc = Market.objects.create(
            exchange_name='MEXC',
            friendly_name='MEXC Testing Interface',
            config_enc='fake-config-hash',
        )
        self.interface_mexc = MEXCMarket({
            'ACCESS_KEY': 'test-api-key',
            'API_SECRET': 'test-api-secret',
        }, self.market_mexc)

        for market in [self.interface_binance, self.interface_kucoin, self.interface_mexc]:
            MarketSymbol.objects.create(market=market.market, base='BTC', quote='USDT')
            MarketSymbol.objects.create(market=market.market, base='ETH', quote='USDT')
            MarketSymbol.objects.create(market=market.market, base='XRP', quote='USDT')
            market.capital = 200
            market.assets = {
                'BTC': 1,
                'ETH': 0.5,
                'XRP': 1000,
            }

    @patch.object(BinanceMarket, 'place_market_order')
    def test_place_valid_buy_order_on_binance(self, mock_place_market_order):
        btc_symbol = MarketSymbol.objects.get(base='BTC', market=self.market_binance)
        mock_place_market_order.return_value = Order(
            status=Order.Status.FILLED,
            symbol=btc_symbol,
            market=self.market_binance,
        )
        order_manager = OrderManager(self.interface_binance)
        try:
            order = order_manager.place(
                MarketSymbol.objects.get(base='BTC', market=self.market_binance), 
                'buy', 
                deal_funds=100,
                silent=False,
                validate=False,
            )
        except Exception as e:
            self.fail(f'Failed to place order: {e}')

    @patch.object(KucoinMarket, 'place_market_order')
    def test_place_valid_buy_order_on_kucoin(self, mock_place_market_order):
        eth_symbol = MarketSymbol.objects.get(base='ETH', market=self.market_kucoin)
        mock_place_market_order.return_value = Order(
            status=Order.Status.FILLED,
            symbol=eth_symbol,
            market=self.market_kucoin,
        )
        order_manager = OrderManager(self.interface_kucoin)
        try:
            order = order_manager.place(
                MarketSymbol.objects.get(base='ETH', market=self.market_kucoin), 
                'buy', 
                deal_funds=100,
                silent=False,
                validate=False,
            )
        except Exception as e:
            self.fail(f'Failed to place order: {e}')

    @patch.object(MEXCMarket, 'place_market_order')
    def test_place_valid_buy_order_on_mexc(self, mock_place_market_order):
        xrp_symbol = MarketSymbol.objects.get(base='XRP', market=self.market_mexc)
        mock_place_market_order.return_value = Order(
            status=Order.Status.FILLED,
            symbol=xrp_symbol,
            market=self.market_mexc,
        )
        order_manager = OrderManager(self.interface_mexc)
        try:
            order = order_manager.place(
                MarketSymbol.objects.get(base='XRP', market=self.market_mexc), 
                'buy', 
                deal_funds=100,
                silent=False,
                validate=False,
            )
        except Exception as e:
            self.fail(f'Failed to place order: {e}')

    @patch.object(BinanceMarket, 'place_market_order')
    def test_place_buy_order_on_binance_insufficient_balance(self, mock_place_market_order):
        btc_symbol = MarketSymbol.objects.get(base='BTC', market=self.market_binance)
        mock_place_market_order.return_value = Order(
            status=Order.Status.REJECTED,
            symbol=btc_symbol,
            market=self.market_binance,
        )
        order_manager = OrderManager(self.interface_binance)
        with self.assertRaises(OrderNotFilledError) as ctx:
            order = order_manager.place(
                MarketSymbol.objects.get(base='BTC', market=self.market_binance), 
                'buy', 
                deal_funds=1000,
                silent=False,
                validate=False,
            )
            self.assertEqual(ctx.exception.order.status, Order.Status.INSUFFICIENT_BALANCE)

    @patch.object(BinanceMarket, 'place_market_order')
    def test_place_buy_order_on_binance_too_much_presicion(self, mock_place_market_order):
        def place_market_order_side_effect(symbol, side, deal_funds, deal_size):
            if deal_funds % 1 != 0:
                raise OrderNotFilledError('filter failure: LOT_SIZE', 
                                          Order(status=Order.Status.REJECTED, symbol=symbol, market=self.market_binance)
                )
            return Order(
                status=Order.Status.FILLED,
                symbol=symbol,
                market=self.market_binance,
            )
        mock_place_market_order.side_effect = place_market_order_side_effect
        btc_symbol = MarketSymbol.objects.get(base='BTC', market=self.market_binance)
        order_manager = OrderManager(self.interface_binance)
        with self.assertRaises(OrderPlacementError) as ctx:
            order = order_manager.place(
                btc_symbol, 
                'buy', 
                deal_funds=100.0000000001,
                silent=False,
                validate=False,
            )
            self.assertIn('LOT_SIZE', ctx.exception.message)

    @patch.object(KucoinMarket, 'place_market_order')
    def test_place_buy_order_on_kucoin_insufficient_balance(self, mock_place_market_order):
        eth_symbol = MarketSymbol.objects.get(base='ETH', market=self.market_kucoin)
        mock_place_market_order.return_value = Order(
            status=Order.Status.REJECTED,
            symbol=eth_symbol,
            market=self.market_kucoin,
        )
        order_manager = OrderManager(self.interface_kucoin)
        with self.assertRaises(OrderNotFilledError) as ctx:
            order = order_manager.place(
                MarketSymbol.objects.get(base='ETH', market=self.market_kucoin), 
                'buy', 
                deal_funds=1000,
                silent=False,
                validate=False,
            )
            self.assertEqual(ctx.exception.order.status, Order.Status.INSUFFICIENT_BALANCE)

    @patch.object(KucoinMarket, 'place_market_order')
    def test_place_buy_order_on_kucoin_too_much_presicion(self, mock_place_market_order):
        def place_market_order_side_effect(symbol, side, deal_funds, deal_size):
            if deal_funds % 1 != 0:
                raise OrderNotFilledError('filter failure: LOT_SIZE', 
                                          Order(status=Order.Status.REJECTED, symbol=symbol, market=self.market_kucoin)
                )
            return Order(
                status=Order.Status.FILLED,
                symbol=symbol,
                market=self.market_kucoin,
            )
        mock_place_market_order.side_effect = place_market_order_side_effect
        eth_symbol = MarketSymbol.objects.get(base='ETH', market=self.market_kucoin)
        order_manager = OrderManager(self.interface_kucoin)
        with self.assertRaises(OrderPlacementError) as ctx:
            order = order_manager.place(
                eth_symbol, 
                'buy', 
                deal_funds=100.0000000001,
                silent=False,
                validate=False,
            )
            self.assertIn('LOT_SIZE', ctx.exception.message)

    @patch.object(MEXCMarket, 'place_market_order')
    def test_place_buy_order_on_mexc_insufficient_balance(self, mock_place_market_order):
        xrp_symbol = MarketSymbol.objects.get(base='XRP', market=self.market_mexc)
        mock_place_market_order.return_value = Order(
            status=Order.Status.REJECTED,
            symbol=xrp_symbol,
            market=self.market_mexc,
        )
        order_manager = OrderManager(self.interface_mexc)
        with self.assertRaises(OrderNotFilledError) as ctx:
            order = order_manager.place(
                MarketSymbol.objects.get(base='XRP', market=self.market_mexc), 
                'buy', 
                deal_funds=1000,
                silent=False,
                validate=False,
            )
            self.assertEqual(ctx.exception.order.status, Order.Status.INSUFFICIENT_BALANCE)

    @patch.object(MEXCMarket, 'place_market_order')
    def test_place_buy_order_on_mexc_too_much_presicion(self, mock_place_market_order):
        def place_market_order_side_effect(symbol, side, deal_funds, deal_size):
            if deal_funds % 1 != 0:
                raise OrderNotFilledError('filter failure: LOT_SIZE', 
                                          Order(status=Order.Status.REJECTED, symbol=symbol, market=self.market_mexc)
                )
            return Order(
                status=Order.Status.FILLED,
                symbol=symbol,
                market=self.market_mexc,
            )
        mock_place_market_order.side_effect = place_market_order_side_effect
        xrp_symbol = MarketSymbol.objects.get(base='XRP', market=self.market_mexc)
        order_manager = OrderManager(self.interface_mexc)
        with self.assertRaises(OrderPlacementError) as ctx:
            order = order_manager.place(
                xrp_symbol, 
                'buy', 
                deal_funds=100.0000000001,
                silent=False,
                validate=False,
            )
            self.assertIn('LOT_SIZE', ctx.exception.message)
