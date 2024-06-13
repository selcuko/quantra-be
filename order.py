import json
import time
import traceback
from typing import Literal

from django.utils import timezone

from logger import logger
from markets import IMarket
from markets.errors import (InsufficientBalance, OrderNotFilledError,
                            OrderPlacementError, OrderPostProcessingError,
                            RejectedOrder)
from markets.helper import float_to_precision
from quantapi.models import GroupOrder, Issue, MarketSymbol, Order, Session, SessionGroup
from utils import can_session_buy, can_session_sell


class OrderManager:
    def __init__(self, market:IMarket, session:'Session|None'=None):
        self.session = session
        self.market = market
        self.account = self.market.account
        self.order  = None

    def place(self, symbol:MarketSymbol, side:Literal['buy', 'sell'], deal_size:float|None=None, deal_funds:float|None=None, validate:bool=True, manual:bool=False, silent:bool=True) -> Order:
        request = {
            'initial_deal_size': deal_size,
            'initial_deal_funds': deal_funds,
            'deal_funds': deal_funds,
            'deal_size': deal_size,
            'side': side,
            'symbol': symbol.name,
            'market': self.market.market.exchange_name,
            'manual': manual,
        }
        deal_size_str = f'{deal_size:f}' if deal_size else None
        deal_funds_str = f'{deal_funds:f}' if deal_funds else None
        if side == 'buy' and deal_funds:
            if symbol.quote_precision:
                deal_funds = float_to_precision(deal_funds, symbol.quote_precision)
                request['deal_funds'] = deal_funds

            filters = self.market.market.filters(symbol)
            if (lot_step := filters.get('lot_step')):
                deal_funds = float_to_precision(deal_funds, lot_step)
                deal_funds_str = f'{deal_funds:f}'
                request['deal_funds'] = deal_funds

        elif side == 'sell' and deal_size:
            if symbol.base_precision:
                deal_size = float_to_precision(deal_size, symbol.base_precision)
                request['deal_size'] = deal_size

            filters = self.market.market.filters(symbol)
            if (lot_step := filters.get('lot_step')):
                deal_size = float_to_precision(deal_size, lot_step)
                deal_size_str = f'{deal_size:f}'
                request['deal_size'] = deal_size
        else:
            print('deal_size:', deal_size, 'deal_funds:', deal_funds, 'side:', side)
            raise ValueError('deal_size for sell or deal_funds for buy must be provided.')
        try:
            order = self.market.place_market_order(symbol, side, deal_funds_str, deal_size_str)
            order.symbol = symbol
            order.placed_at = timezone.now()
            order.account = self.account
            order.save()
        except (RejectedOrder, InsufficientBalance) as e:
            order = Order.objects.create(
                side=Order.Side.BUY if side == 'buy' else Order.Side.SELL,
                deal_size=deal_size,
                deal_funds=deal_funds,
                status=Order.Status.REJECTED if isinstance(e, RejectedOrder) else Order.Status.INSUFFICIENT_BALANCE,
                details=traceback.format_exc(),
                messages_raw=f'RejectedOrder: {e!r}',
                account=self.market.account,
                symbol=symbol,
            )
        except OrderPostProcessingError as e:
            if not e.oid:
                raise e
            order = self.market.get_order(symbol, e.oid)
            order = Order.objects.get_or_create(oid=order.oid, defaults={
                'side': Order.Side.BUY if side == 'buy' else Order.Side.SELL,
                'deal_size': deal_size,
                'deal_funds': deal_funds,
                'status': order.status,
                'market': self.market.market,
                'symbol': symbol,
                'price': order.price or json.loads(self.market.market.prices or '{}').get(symbol.base),
            })[0]
        except Exception as e:
            raise OrderPlacementError(f'Error placing order: {e!r}')

        if validate and order.oid:
            validation_tries = 0
            while order.status != Order.Status.FILLED and order.status not in [Order.Status.REJECTED, Order.Status.INSUFFICIENT_BALANCE] and validation_tries < 5:
                time.sleep(0.5)
                order = self.market.get_order(symbol, order)
                validation_tries += 1

        if not order.status == Order.Status.FILLED and not silent:
            order.save()
            raise OrderNotFilledError(f'Order not filled, status is {order.status} ({order.oid=}).', order=order)

        if self.session:
            order.session = self.session
        if manual:
            order.force = True
        if not order.side:
            order.side = Order.Side.BUY if side == 'buy' else Order.Side.SELL
        order.account = self.account
        order.symbol = symbol
        order.request = json.dumps(request)
        order.save()

        return order


class GroupOrderManager:
    def __init__(self, group:SessionGroup):
        self.group = group
        self.market = group.market
        self.sessions = group.sessions.all()


    def place(self, side:Literal['buy', 'sell']) -> GroupOrder:
        group_order = GroupOrder.objects.create(
            group=self.group,
            side=side.upper(),
            status=GroupOrder.Status.PENDING,
        )
        orders = {}
        for session in self.sessions:
            if side == 'buy' and not can_session_buy(session):
                continue
            if side == 'sell' and not can_session_sell(session):
                continue
            interface = session.account.get_interface()
            manager   = OrderManager(interface, session)
            try:
                order = manager.place(self.group.symbol, side, deal_funds=session.capital, deal_size=session.assets, validate=False)
            except Exception as exc:
                issue = Issue.from_exception(exc)
                issue.object = session.account
                issue.level = Issue.Level.CRITICAL
                issue.save()
                logger.critical(f'Error placing order for {session.account}: {exc!r}')
                continue
            order.group = group_order # type: ignore
            order.save()
            group_order.deal_funds += order.deal_funds if order.deal_funds else 0
            group_order.deal_size  += order.deal_size if order.deal_size else 0
            if order.status == Order.Status.FILLED and group_order.status != GroupOrder.Status.PARTIAL:
                group_order.status = GroupOrder.Status.FILLED
            elif group_order.status == GroupOrder.Status.FILLED:
                group_order.status = GroupOrder.Status.PARTIAL
            orders[session] = order
        if group_order.status == GroupOrder.Status.PENDING:
            group_order.status = GroupOrder.Status.EXPIRED
        group_order.save()
        return group_order
