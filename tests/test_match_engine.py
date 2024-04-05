from datetime import datetime
from django.test import TestCase
import pytz
from match import MatchEngine, get_start_end_dates


class MatchEngineTests(TestCase):
    def test_start_and_end_dates(self):
        ts = datetime(2024, 1, 1, 23, 58)
        start, end = get_start_end_dates(ts, 15)
        self.assertEqual(start, datetime(2024, 1, 1, 23, 45))
        self.assertEqual(end, datetime(2024, 1, 2, 0, 0))

        ts = datetime(2024, 1, 1, 12, 0)
        start, end = get_start_end_dates(ts, 60)
        self.assertEqual(start, datetime(2024, 1, 1, 12, 0))
        self.assertEqual(end, datetime(2024, 1, 1, 13, 0))

        ts = datetime(2024, 1, 1, 5, 44, 12)
        start, end = get_start_end_dates(ts, 15)
        self.assertEqual(start, datetime(2024, 1, 1, 5, 30))
        self.assertEqual(end, datetime(2024, 1, 1, 5, 45))

        ts = datetime(2023, 12, 31, 23, 55, 48)
        start, end = get_start_end_dates(ts, 1)
        self.assertEqual(start, datetime(2023, 12, 31, 23, 55))
        self.assertEqual(end, datetime(2023, 12, 31, 23, 56))

        ts = datetime(2023, 12, 31, 23, 55, 48)
        start, end = get_start_end_dates(ts, 60 * 24)
        self.assertEqual(start, datetime(2023, 12, 31, 0, 0))
        self.assertEqual(end, datetime(2024, 1, 1, 0, 0))

    def test_candle_formation_1min(self):
        candles = []
        def callback(candle):
            candles.append(candle)
        engine = MatchEngine('1 min', callback)

        messages = [
            { 'time': datetime(2024, 1, 1, 0, 0), 'price': 5, 'size': 10, 'maker': True },
            { 'time': datetime(2024, 1, 1, 0, 0), 'price': 8, 'size': 18, 'maker': False },
            { 'time': datetime(2024, 1, 1, 0, 1), 'price': 2, 'size': 7, 'maker': True },
            { 'time': datetime(2024, 1, 1, 0, 1), 'price': 5, 'size': 1, 'maker': True },
            { 'time': datetime(2024, 1, 1, 0, 2), 'price': 1, 'size': 99, 'maker': False },
            { 'time': datetime(2024, 1, 1, 0, 3), 'price': 10, 'size': 2, 'maker': False },
        ]

        for msg in messages:
            engine.on_match(msg)

        self.assertEqual(len(candles), 3)
        candle = candles[0]
        self.assertEqual(candle['open'], 5)
        self.assertEqual(candle['close'], 8)
        self.assertEqual(candle['time'], datetime(2024, 1, 1, 0, 0, 0, tzinfo=pytz.UTC))
        self.assertEqual(candle['end'], datetime(2024, 1, 1, 0, 1, 0, tzinfo=pytz.UTC))

    def test_candle_formation_15min(self):
        candles = []
        def callback(candle):
            candles.append(candle)
        engine = MatchEngine('15 min', callback)

        messages = [
            { 'time': datetime(2024, 1, 1, 0, 0), 'price': 5, 'size': 10, 'maker': True },
            { 'time': datetime(2024, 1, 1, 0, 2), 'price': 8, 'size': 18, 'maker': False },
            { 'time': datetime(2024, 1, 1, 0, 8), 'price': 2, 'size': 7, 'maker': True },
            { 'time': datetime(2024, 1, 1, 0, 14), 'price': 15, 'size': 1, 'maker': True },
            { 'time': datetime(2024, 1, 1, 0, 16), 'price': 1, 'size': 99, 'maker': False },
            { 'time': datetime(2024, 1, 1, 0, 28), 'price': 10, 'size': 2, 'maker': False },
            { 'time': datetime(2024, 1, 1, 0, 29), 'price': 5, 'size': 10, 'maker': True },
            { 'time': datetime(2024, 1, 1, 0, 30), 'price': 8, 'size': 18, 'maker': False },
            { 'time': datetime(2024, 1, 1, 0, 34), 'price': 2, 'size': 7, 'maker': True },
            { 'time': datetime(2024, 1, 1, 0, 38), 'price': 5, 'size': 1, 'maker': True },
            { 'time': datetime(2024, 1, 1, 0, 40), 'price': 1, 'size': 99, 'maker': False },
            { 'time': datetime(2024, 1, 1, 0, 45), 'price': 5, 'size': 10, 'maker': True },
            { 'time': datetime(2024, 1, 1, 0, 48), 'price': 8, 'size': 18, 'maker': False },
        ]

        for msg in messages:
            engine.on_match(msg)

        self.assertEqual(len(candles), 3)
        candle = candles[0]
        self.assertEqual(candle['time'], datetime(2024, 1, 1, 0, 0, tzinfo=pytz.UTC))
        self.assertEqual(candle['end'], datetime(2024, 1, 1, 0, 15, tzinfo=pytz.UTC))
        self.assertEqual(candle['open'], 5)
        self.assertEqual(candle['close'], 15)
        
