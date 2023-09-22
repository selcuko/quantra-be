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
        start = datetime.fromtimestamp(float(start_str))
        end = datetime.fromtimestamp(float(end_str))
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

        
