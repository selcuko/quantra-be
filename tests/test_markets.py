from datetime import datetime, timedelta
from tests import QuantTestBase
import unittest
from unittest import mock
from markets import get_market
from binance.client import Client as BinanceClient
from models import interval_to_minutes

class BinanceTests(QuantTestBase):

    @mock.patch('binance.client.Client')
    def setUp(self, mock_client):
        self.market = get_market('BINANCE')
    
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

