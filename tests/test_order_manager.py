from unittest import mock
from markets.errors import RejectedOrder
from order import GroupOrderManager, OrderManager
from quantapi.models import MarketAccount, MarketCredentials, Order, SessionGroup
from tests.core import QuantTestCase
from tests.mocks import mock_get_interface
from logger import logger

class OrderManagerTests(QuantTestCase):
    def setUp(self):
        self.setup_market()
        self.setup_account()
        self.setup_session()
        self.account.capital = 2000
        self.account.assets = '{ "BTC": 2 }'
        self.account.save()
        self.session.capital = 1000
        self.session.assets = 1
        self.session.save()

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
        self.account.capital = 1000
        self.account.save()
        om = self.get_manager()
        order = om.place(self.symbol, 'buy', deal_funds=10, validate=False, silent=False)
        self.assertIsNotNone(order)
        self.assertEqual(order.symbol, self.symbol)
        self.assertEqual(order.side, Order.Side.BUY)
        self.assertEqual(order.deal_funds, 10)
        self.assertEqual(order.status, Order.Status.FILLED)
        self.session.refresh_from_db()
        self.assertEqual(self.session.capital, 990)
        self.assertEqual(self.session.assets, 1.0002)

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

    @mock.patch.object(MarketAccount, 'refresh')
    def test_om_can_place_sell_order(self, mock_refresh):
        # define a mock_refresh function
        def refresh(market, force=False):
            self.account.capital = 6000
            self.account.assets = '{ "BTC": 0.9 }'
            self.account.save()
        mock_refresh.side_effect = refresh
        self.account.assets = '{ "BTC": 1 }'
        om = self.get_manager()
        order = om.place(self.symbol, 'sell', deal_size=0.1, validate=False, silent=False)
        self.assertIsNotNone(order)
        self.assertEqual(order.symbol, self.symbol)
        self.assertEqual(order.side, Order.Side.SELL)
        self.assertEqual(order.deal_size, 0.1)
        self.assertEqual(order.status, Order.Status.FILLED)
        self.session.refresh_from_db()
        self.assertEqual(self.session.capital, 6000.0)
        self.assertEqual(self.session.assets, 0.9)

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


class GroupOrderManagerTests(QuantTestCase):
    def setUp(self):
        self.setup_market()
        self.setup_strategy()
        self.setup_symbol('BTC-USDT')
        self.credentials1 = MarketCredentials.objects.create(
            market=self.market,
            encrypted='{"fake": "credendials"}',
            owner='John Nash'
        )
        self.credentials2 = MarketCredentials.objects.create(
            market=self.market,
            encrypted='{"fake": "credendials"}',
            owner='Joe Dasher'
        )
        self.account1 = MarketAccount.objects.get(credentials=self.credentials1)
        self.account2 = MarketAccount.objects.get(credentials=self.credentials2)

        self.group = SessionGroup.objects.create(
            symbol=self.symbol,
            market=self.market,
            strategy=self.strategy,
            freq='5 min',
            status=SessionGroup.Status.PLANNED
        )
        self.session1 = self.group.add_account(self.account1)
        self.session2 = self.group.add_account(self.account2)

    def get_manager(self):
        return GroupOrderManager(self.group)

    def test_gom_initializes_correctly(self):
        gom = GroupOrderManager(self.group)
        self.assertEqual(gom.group, self.group)
        self.assertEqual(gom.market, self.group.market)
        self.assertEqual(len(gom.sessions), 2)

    @mock.patch.object(MarketAccount, 'get_interface', mock_get_interface)
    @mock.patch.object(MarketAccount, 'refresh')
    def test_gom_can_place_buy_order(self, mock_refresh):
        logger.disabled = False
        def refresh(market, force=False):
            self.account1.capital = 1000
            self.account1.assets = '{ "BTC": 0.02 }'
            self.account2.capital = 2000
            self.account2.assets = '{ "BTC": 0.04 }'
            self.account1.save()
            self.account2.save()
            self.session1.capital = 0
            self.session1.assets = 0.02
            self.session2.capital = 0
            self.session2.assets = 0.04
            self.session1.save()
            self.session2.save()
        mock_refresh.side_effect = refresh
        self.account1.capital = 1000
        self.account2.capital = 2000
        self.account1.save()
        self.account2.save()
        self.session1.capital = 1000
        self.session2.capital = 2000
        self.session1.save()
        self.session2.save()

        gom = self.get_manager()
        group_order = gom.place('buy')
        assert group_order is not None
        orders = group_order.orders.all()
        self.assertEqual(len(orders), 2)
        self.assertEqual(orders[0].account, self.account1)
        self.assertEqual(orders[1].account, self.account2)
        self.assertEqual(orders[0].deal_funds, 1000)
        self.assertEqual(orders[0].deal_size, 0.02)
        self.assertEqual(orders[1].deal_funds, 2000)
        self.assertEqual(orders[1].deal_size, 0.04)

       
        self.assertEqual(group_order.group, self.group)
        self.assertEqual(group_order.side, Order.Side.BUY)
        self.assertEqual(group_order.status, Order.Status.FILLED)
        self.assertEqual(group_order.signal, None)
        self.assertEqual(group_order.deal_funds, 3000)
        self.assertEqual(group_order.deal_size, 0.06)
        self.assertEqual(group_order.manual, False)

        self.account1.refresh_from_db()
        self.account2.refresh_from_db()
        self.session1.refresh_from_db()
        self.session2.refresh_from_db()
        self.assertEqual(self.session1.capital, 0)
        self.assertEqual(self.session1.assets, 0.02)
        self.assertEqual(self.session2.capital, 0)
        self.assertEqual(self.session2.assets, 0.04)

    @mock.patch.object(MarketAccount, 'get_interface', mock_get_interface)
    def test_gom_can_handle_second_buy_call(self):
        # ensure that a second buy signal doesn't make us go over budget
        self.account1.assets = '{ "BTC": 0.02 }'
        self.account2.assets = '{ "BTC": 0.04 }'
        self.account1.save()
        self.account2.save()
        self.session1.assets = 0.02
        self.session2.assets = 0.04
        self.session1.save()
        self.session2.save()

        gom = self.get_manager()
        group_order = gom.place('buy')
        self.assertIsNone(group_order)

        self.account1.refresh_from_db()
        self.account2.refresh_from_db()
        self.session1.refresh_from_db()
        self.session2.refresh_from_db()
        self.assertEqual(self.session1.capital, 0)
        self.assertEqual(self.session1.assets, 0.02)
        self.assertEqual(self.session2.capital, 0)
        self.assertEqual(self.session2.assets, 0.04)




