
# write django test class
from datetime import datetime
from django.test import TestCase
from match import get_start_end_dates


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
