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
from quantapi.models import MarketSymbol, Order, Session


class OrderManager:
    def __init__(self, market:IMarket, session:'Session|None'=None):
        self.session = session
        self.market = market
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
            raise ValueError('deal_size for sell or deal_funds for buy must be provided.')
        try:
            order = self.market.place_market_order(symbol, side, deal_funds_str, deal_size_str)
            order.symbol = symbol
            order.placed_at = timezone.now()
            order.market = self.market.market
            order.save()
        except (RejectedOrder, InsufficientBalance) as e:
            order = Order.objects.create(
                side=Order.Side.BUY if side == 'buy' else Order.Side.SELL,
                deal_size=deal_size,
                deal_funds=deal_funds,
                status=Order.Status.REJECTED if isinstance(e, RejectedOrder) else Order.Status.INSUFFICIENT_BALANCE,
                details=traceback.format_exc(),
                messages_raw=f'RejectedOrder: {e!r}',
                market=self.market.market,
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
        order.market = self.market.market
        order.symbol = symbol
        order.request = json.dumps(request)
        order.save()

        return order
