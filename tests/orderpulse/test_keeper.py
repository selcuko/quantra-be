from random import randint
from unittest import mock
from orderpulse.keeper import BookKeeper, KeeperPool
from quantapi.models import Market
from tests.core import QuantTestCase
from tests.mocks import market_get_interface


class KeeperTests(QuantTestCase):
    def setUp(self):
        self.setup_symbol('BTC-USDT')
        self.snapshot = {
            'bids': [
                { 'price': 100, 'size': 50 },
                { 'price': 110, 'size': 20 },
                { 'price': 120, 'size': 30 }
            ],
            'asks': [
                { 'price': 130, 'size': 10 },
                { 'price': 140, 'size': 40 },
                { 'price': 150, 'size': 60 }
            ]
        }
        self.valid_update = {  # price moved to 140
            'bids': [
                { 'price': 100, 'size': 30 },
                { 'price': 110, 'size': 10 },
                { 'price': 120, 'size': 0 },
                { 'price': 140, 'size': 70 }
            ],
            'asks': [
                { 'price': 130, 'size': 0 },
                { 'price': 140, 'size': 0 },
                { 'price': 150, 'size': 80 },
                { 'price': 160, 'size': 20 }
            ]
        }
        self.sloppy_update = {  # price moved to 140, size not set to 0 for overlap
            'bids': [
                { 'price': 100, 'size': 30 },
                { 'price': 110, 'size': 10 },
                { 'price': 140, 'size': 70 }
            ],
            'asks': [
                { 'price': 150, 'size': 80 },
                { 'price': 160, 'size': 20 }
            ]
        }

    def get_bids(self, px_start, px_end, count=10):
        steps = (px_end - px_start) // count
        return [{ 'price': randint(px_start, px_end), 'size': randint(1, 100) } for i in range(px_start, px_end, steps)]

    def get_keeper(self):
        return BookKeeper(self.symbol)

    @mock.patch.object(Market, 'get_interface', market_get_interface)
    def test_keeper_snapshot_applied_correctly(self):
        keeper = self.get_keeper()
        keeper.on_snapshot(self.snapshot)
        bids, asks = keeper.book.get_bids(), keeper.book.get_asks()
        self.assertEqual(bids[-1].price, 120)
        self.assertEqual(bids[-1].size, 30)
        self.assertEqual(bids[0].price, 100)
        self.assertEqual(bids[0].size, 50)
        self.assertEqual(asks[0].price, 130)
        self.assertEqual(asks[0].size, 10)
        self.assertEqual(asks[-1].price, 150)
        self.assertEqual(asks[-1].size, 60)

    @mock.patch.object(Market, 'get_interface', market_get_interface)
    def test_keeper_valid_update_applied_correctly(self):
        keeper = self.get_keeper()
        keeper.on_snapshot(self.snapshot)
        keeper.on_update(self.valid_update)
        bids, asks = keeper.book.get_bids(), keeper.book.get_asks()
        self.assertEqual(bids[-1].price, 140)
        self.assertEqual(bids[-1].size, 70)
        self.assertEqual(bids[0].price, 100)
        self.assertEqual(bids[0].size, 30)
        self.assertEqual(asks[0].price, 150)
        self.assertEqual(asks[0].size, 80)
        self.assertEqual(asks[-1].price, 160)
        self.assertEqual(asks[-1].size, 20)

    @mock.patch.object(Market, 'get_interface', market_get_interface)
    @mock.patch.object(Market, 'get_interface', market_get_interface)
    def test_keeper_sloppy_update_applied_correctly(self):
        keeper = KeeperPool.get(self.symbol)
        keeper.on_snapshot(self.snapshot)
        keeper.on_update(self.sloppy_update)
        bids, asks = keeper.book.get_bids(), keeper.book.get_asks()
        self.assertEqual(bids[-1].price, 140)
        self.assertEqual(bids[-1].size, 70)
        self.assertEqual(bids[0].price, 100)
        self.assertEqual(bids[0].size, 30)
        self.assertEqual(asks[0].price, 150)
        self.assertEqual(asks[0].size, 80)
        self.assertEqual(asks[-1].price, 160)
        self.assertEqual(asks[-1].size, 20)
