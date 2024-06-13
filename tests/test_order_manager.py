from unittest import mock
from markets.errors import RejectedOrder
from order import OrderManager
from quantapi.models import MarketAccount, Order
from tests.core import QuantTestCase
from tests.mocks import mock_get_interface


class OrderManagerTests(QuantTestCase):
    def setUp(self):
        self.setup_market()
        self.setup_account()
        self.setup_session()

    @mock.patch.object(MarketAccount, 'get_interface', mock_get_interface)
    def get_interface(self):
        return self.account.get_interface()

    def get_manager(self):
        return OrderManager(self.get_interface(), self.session)

    def test_om_initializes_correctly(self):
        interface = self.get_interface()
        om = OrderManager(interface, self.session)
        self.assertEqual(om.session, self.session)
        self.assertEqual(om.account, self.account)
        self.assertEqual(om.market, interface)
        self.assertIsNone(om.order)

    def test_om_can_place_buy_order(self):
        om = self.get_manager()
        order = om.place(self.symbol, 'buy', deal_funds=10, validate=False, silent=False)
        self.assertIsNotNone(order)
        self.assertEqual(order.symbol, self.symbol)
        self.assertEqual(order.side, Order.Side.BUY)
        self.assertEqual(order.deal_funds, 10)
        self.assertEqual(order.status, Order.Status.FILLED)

    def test_om_overbudget_buy_order(self):
        om = self.get_manager()
        order = om.place(self.symbol, 'buy', deal_funds=1000000, validate=False)
        self.assertIsNotNone(order)
        self.assertEqual(order.symbol, self.symbol)
        self.assertEqual(order.side, Order.Side.BUY)
        self.assertEqual(order.deal_funds, 1000000)
        self.assertEqual(order.status, Order.Status.INSUFFICIENT_BALANCE)

    def test_om_negative_buy_order(self):
        om = self.get_manager()
        with self.assertRaises(RejectedOrder):
            om.place(self.symbol, 'buy', deal_funds=-10, validate=False)

    def test_om_can_place_sell_order(self):
        om = self.get_manager()
        order = om.place(self.symbol, 'sell', deal_size=0.1, validate=False, silent=False)
        self.assertIsNotNone(order)
        self.assertEqual(order.symbol, self.symbol)
        self.assertEqual(order.side, Order.Side.SELL)
        self.assertEqual(order.deal_size, 0.1)
        self.assertEqual(order.status, Order.Status.FILLED)

    def test_om_overbudget_sell_order(self):
        om = self.get_manager()
        order = om.place(self.symbol, 'sell', deal_size=1000000, validate=False)
        self.assertIsNotNone(order)
        self.assertEqual(order.symbol, self.symbol)
        self.assertEqual(order.side, Order.Side.SELL)
        self.assertEqual(order.deal_size, 1000000)
        self.assertEqual(order.status, Order.Status.INSUFFICIENT_BALANCE)

    def test_om_negative_sell_order(self):
        om = self.get_manager()
        with self.assertRaises(RejectedOrder):
            om.place(self.symbol, 'sell', deal_size=-10, validate=False)
