from unittest import mock
from orderpulse.consolidator import BookAggregator
from orderpulse.keeper import BookKeeper
from quantapi.models import Market
from tests.core import QuantTestCase
from tests.mocks import market_get_interface


ex1_snapshot = {
    'bids': [
        { 'price': 110, 'size': 20 },
        { 'price': 100, 'size': 50 },
        { 'price': 120, 'size': 30 },
    ],
    'asks': [
        { 'price': 130, 'size': 10 },
        { 'price': 140, 'size': 40 },
        { 'price': 150, 'size': 60 },
    ]
}

ex2_snapshot = {
    'bids': [
        { 'price': 112, 'size': 16 },
        { 'price': 110, 'size': 24 },
        { 'price': 124, 'size': 41 },
    ],
    'asks': [
        { 'price': 138, 'size': 2 },
        { 'price': 140, 'size': 39 },
        { 'price': 145, 'size': 18 },
    ]
}

ex1_valid_update = {
    
}

class AggregatorTests(QuantTestCase):
    @mock.patch.object(Market, 'get_interface', market_get_interface)
    def setUp(self):
        self.market1 = self.setup_market('EX-1')
        self.market2 = self.setup_market('EX-2')
        self.symbol1 = self.setup_symbol('BTC-USDT', self.market1)
        self.symbol2 = self.setup_symbol('BTC-USDT', self.market2)
        self.keeper1 = BookKeeper(self.symbol1)
        self.keeper2 = BookKeeper(self.symbol2)
        self.keeper1.interface.name = 'EX-1'
        self.keeper2.interface.name = 'EX-2'

    def get_aggregator(self):
        return BookAggregator('BTC-USDT')

    def test_aggregator_applies_initial_keeper_snaptshot(self):
        self.keeper1.on_snapshot(ex1_snapshot)
        keeper_bids, keeper_asks = self.keeper1.book.get_bids(), self.keeper1.book.get_asks()
        self.assertEqual(len(keeper_bids), 3)
        self.assertEqual(len(keeper_asks), 3)
        aggregator = self.get_aggregator()
        aggregator.add_keeper(self.keeper1, start=False)
        bids, asks = aggregator.book.get_bids(), aggregator.book.get_asks()
        self.assertEqual(len(bids), 3)
        self.assertEqual(len(asks), 3)
        self.assertEqual(bids[-1].price, 120)
        self.assertEqual(bids[-1].size, 30)
        self.assertEqual(bids[0].price, 100)
        self.assertEqual(bids[0].size, 50)
        self.assertEqual(asks[0].price, 130)
        self.assertEqual(asks[0].size, 10)
        self.assertEqual(asks[-1].price, 150)
        self.assertEqual(asks[-1].size, 60)

    def test_aggregator_applies_second_keeper_snapshot(self):
        self.keeper1.on_snapshot(ex1_snapshot)
        self.keeper2.on_snapshot(ex2_snapshot)
        aggregator = self.get_aggregator()
        aggregator.add_keeper(self.keeper1, start=False)
        aggregator.add_keeper(self.keeper2, start=False)
        bids, asks = aggregator.book.get_bids(), aggregator.book.get_asks()
        self.assertEqual(len(bids), 5)
        self.assertEqual(len(asks), 5)
        self.assertEqual(bids[-1].price, 124)
        self.assertEqual(bids[-1].size, 41)
        self.assertEqual(bids[0].price, 100)
        self.assertEqual(bids[0].size, 50)
        self.assertEqual(asks[0].price, 130)
        self.assertEqual(asks[0].size, 10)
        self.assertEqual(asks[-1].price, 150)
        self.assertEqual(asks[-1].size, 60)
