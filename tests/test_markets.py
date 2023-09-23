from datetime import datetime, timedelta
from random import randint
import uuid
from tests import QuantTestBase
import unittest
from unittest import mock
from markets import get_market
from binance.client import Client as BinanceClient
from models import Order, interval_to_minutes

class BinanceTests(QuantTestBase):

    @mock.patch.object(BinanceClient, 'get_account')
    def setUp(self, mock_get_account):
        mock_get_account.return_value = {}
        self.market = get_market('BINANCE', {'API_KEY': 'apikey', 'API_SECRET': 'apisecret', 'TESTNET': True})
    
    def mock_get_historical_klines(self, symbol:str, interval:str, start_str:str, end_str:str, limit:int=500):
        inv_map = {
            '1m': 1,
            '3m': 3,
            '5m': 5,
            '15m': 15,
        }
        interval = inv_map[interval]
        start = self.market._standardize_datetime(start_str)
        end = self.market._standardize_datetime(end_str)
        klines = []
        dtloop = start
        for i in range(limit):
            klines.append([
                dtloop.timestamp()*1000,
                0.1*i+1,
                0.2*i+1,
                0.3*i+1,
                0.4*i+1,
                0.5*i+1,
            ])
            dtloop += timedelta(minutes=interval)
            if dtloop > end:
                break
        return klines

    def mock_create_order(self, symbol:str, side:str, type:str, quantity:float=None, funds:float=None, price:float=None, newClientOrderId:str=None, quoteOrderQty:float=None, stopPrice:float=None, icebergQty:float=None, newOrderRespType:str=None, recvWindow:int=None, timeInForce:str=None):
        assert quantity or funds if type == 'MARKET' else price and quantity, f'Must specify quantity or funds for market orders, or price and quantity for limit orders (type={type}, qty={quantity}, funds={funds}, price={price})'
        price = '0.00000000' if not price else str(price)
        quantity = '0.00000000' if not quantity else str(quantity)
        funds = '0.00000000' if not funds else str(funds)
        status = 'FILLED' if type == 'MARKET' else 'NEW'
        return {
            'symbol': self.market._format_symbol(symbol), 
            'orderId': randint(1000000000, 9999999999),
            'orderListId': -1, 
            'clientOrderId': newClientOrderId, 
            'transactTime': datetime.now().timestamp() * 1000, 
            'price': price, 
            'origQty': quantity, 
            'executedQty': quantity, 
            'cummulativeQuoteQty': funds, 
            'status': status, 
            'timeInForce': 'GTC', 
            'type': type, 
            'side': side, 
            'workingTime': datetime.now().timestamp() * 1000, 
            'fills': [], 
            'selfTradePreventionMode': 'NONE'
        }

    @mock.patch.object(uuid, 'uuid4')
    @mock.patch.object(BinanceClient, 'create_order')
    def test_place_market_order(self, mock_create_order, mock_uuid4):
        mock_create_order.side_effect = self.mock_create_order
        mock_uuid4.return_value = uuid.UUID('12345678-1234-1234-1234-123456789012')

        order: Order = self.market.place_market_order('BTC-USDT', 'buy', funds=50)
        args, kwargs = mock_create_order.call_args
        self.assertEqual(kwargs['symbol'], 'BTCUSDT')
        self.assertEqual(kwargs['side'], 'BUY')
        self.assertEqual(kwargs['type'], 'MARKET')
        self.assertEqual(kwargs['quantity'], '0.00000000')
        self.assertEqual(kwargs['funds'], '50.00000000')
        self.assertEqual(kwargs['price'], '0.00000000')
        self.assertEqual(kwargs['newClientOrderId'], None)
        self.assertEqual(order.symbol.name, 'BTC-USDT')


    @mock.patch.object(BinanceClient, 'get_historical_klines')
    def test_get_last_klines(self, mock_get_historical_klines):
        mock_get_historical_klines.side_effect = self.mock_get_historical_klines

        limit = 1
        klines = self.market.get_last_klines('BTC-USDT', '1 min', limit)
        dtnow = datetime.now()
        self.assertEqual(len(klines), limit)
        expected_start = self.market._format_datetime(dtnow-timedelta(minutes=limit))
        expected_end = self.market._format_datetime(dtnow)
        mock_get_historical_klines.assert_called_once_with(
            symbol='BTCUSDT', 
            interval='1m',
            limit=limit,
            start_str=expected_start,
            end_str=expected_end,
        )

        limit = 5
        klines = self.market.get_last_klines('BTC-USDT', '1 min', limit)
        dtnow = datetime.now()
        self.assertEqual(len(klines), limit)
        expected_start = self.market._format_datetime(dtnow-timedelta(minutes=limit))
        expected_end = self.market._format_datetime(dtnow)
        mock_get_historical_klines.assert_called_with(
            symbol='BTCUSDT', 
            interval='1m',
            limit=limit,
            start_str=expected_start,
            end_str=expected_end,
        )

    @mock.patch.object(BinanceClient, 'get_historical_klines')
    def test_get_klines(self, mock_get_historical_klines):
        mock_get_historical_klines.side_effect = self.mock_get_historical_klines

        start = datetime(2020, 1, 1, 5, 5)
        end = datetime(2020, 1, 1, 5, 15)
        klines = self.market.get_klines('BTC-USDT', '5 min', start, end)
        self.assertEqual(len(klines), 3)
        expected_start = self.market._format_datetime(start)
        expected_end = self.market._format_datetime(end)
        mock_get_historical_klines.assert_called_once_with(
            symbol='BTCUSDT', 
            interval='5m',
            limit=1000,
            start_str=expected_start,
            end_str=expected_end,
        )
    
    def test_json(self):
        json = self.market.json()
        self.assertEqual(json['name'], 'BINANCE')
        self.assertFalse(json['authenticated'])
        self.assertFalse(json['testnet'])
    
    def test_formatting_and_standardizing(self):
        dtime = datetime(2020, 1, 1, 5, 5)
        self.assertEqual(self.market._format_datetime(dtime), '1577844300000')

        symbol = 'btc-USDT'
        self.assertEqual(self.market._format_symbol(symbol), 'BTCUSDT')

        interval = '15 min'
        self.assertEqual(self.market._format_interval(interval), '15m')

        kline = ['1577844300000', '1', '2', '3', '4', '5']
        self.assertEqual(self.market._standardize_klines([kline]), [
            [datetime(2020, 1, 1, 5, 5), 1, 2, 3, 4, 5]
        ])

        symbol = {'baseAsset': 'BTC', 'quoteAsset': 'USDT'}
        self.assertEqual(self.market._standardize_symbol(symbol), 'BTC-USDT')

        dtstr = '1577844300000'
        self.assertEqual(self.market._standardize_datetime(dtstr), datetime(2020, 1, 1, 5, 5))
