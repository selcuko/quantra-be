import json
from typing import Literal
from rest_framework import serializers
from markets.errors import InsufficientBalance
from quantapi.models import Market, MarketAccount, MarketSymbol, Order, Session


class InvalidRequestError(Exception):
    status_code = 400
    detail = 'Validation failed.'

    def __init__(self, detail: str = ''):
        if detail:
            self.detail = detail


def validate_symbol_against_market(symbol: 'MarketSymbol', market: 'Market') -> bool:
    """
    Validate that the symbol can be used for a Session.
    """
    if not symbol or not symbol.pk:
        raise InvalidRequestError('Symbol is required')
    if not market or not market.pk:
        raise InvalidRequestError('Market is required')
    if symbol.market != market:
        raise InvalidRequestError(f'Symbol\'s market {symbol.market.exchange_name} does not match the market {market.exchange_name}')
    if not symbol.spot_trading_enabled:
        raise InvalidRequestError(f'Spot trading is not enabled for {symbol.base} in {market.exchange_name}')
    return True

def validate_session_can_start(session: 'Session'):
    """
    Validate that the session can start.
    """
    if not session or not session.pk:
        raise InvalidRequestError('Session is required')
    # Disabling the check below as a workaround to resume ERROR sessions
    # if session.status not in [Session.Status.PLANNED, Session.Status.PAUSED, Session.Status.ONGOING]:
    #     raise InvalidRequestError(f'Session is not in a state that can be started: {session.status}')
    if session.equity < 5:
        raise InvalidRequestError(f'Session equity (${session.equity}) is too low to start trading (minimum is $5)')
    if session.group:
        raise InvalidRequestError('Session is part of a group and cannot be started individually')
    return True
def validate_session_can_save(session: 'Session'):
    """
    Validate that the session can be saved.
    """
    if not session:
        raise InvalidRequestError('Session is required')
    if session.capital < 0:
        raise InvalidRequestError('Capital cannot be negative')
    if session.capital > (session.account.capital or 0):
        raise InvalidRequestError(f'Session capital (${session.capital}) cannot exceed account capital (${session.account.capital or 0})')
    account_assets = json.loads(session.account.assets or '{}')
    available_assets = account_assets.get(session.symbol.base, 0)
    if session.assets > available_assets:
        raise InvalidRequestError(f'Session assets ({session.assets}) cannot exceed available assets ({available_assets})')
    return True
def validate_order_payload(account: MarketAccount, symbol: MarketSymbol, side: Literal['BUY', 'SELL'], 
                           deal_size: 'float|None', funds: 'float|None', session: 'Session|None' = None):
    account_assets = json.loads(account.assets or '{}').get(symbol.base, 0)
    price = json.loads(account.market.prices or '{}').get(f'{symbol.base}-USDT', 0)
    if not symbol.market == account.market:
        raise serializers.ValidationError('symbol.market should be the same as account.market')
    if not symbol.spot_trading_enabled:
        raise serializers.ValidationError('Spot trading is not enabled for this symbol')
    if side == Order.Side.BUY:
        if not funds:
            raise serializers.ValidationError('funds is required for BUY orders')
        elif session and funds > session.capital:
            raise InsufficientBalance(f'You tried to buy with ${funds} but you only have ${session.capital:.2f} in your session.')
        elif funds > account.capital:
            raise InsufficientBalance(f'You tried to buy with ${funds} but you only have ${account.capital:.2f} in your account.')
        elif funds < 5:
            raise InvalidRequestError(f'You tried to buy with ${funds} but minimum amount is $5.')
    if side == Order.Side.SELL:
        if not deal_size:
            raise serializers.ValidationError('deal_size is required for SELL orders')
        elif session and deal_size > session.assets:
            raise InsufficientBalance(f'You tried to sell {deal_size} {symbol.base} but you only have {session.assets} {symbol.base} in your session.')
        elif deal_size > account_assets:
            raise InsufficientBalance(f'You tried to sell {deal_size} {symbol.base} but you only have {account_assets} {symbol.base} in your account.')
        elif deal_size * price < 5:
            raise InvalidRequestError(f'You tried to sell {deal_size} {symbol.base} (${deal_size * price}) but the value is less than $5.')
    if funds and deal_size:
        raise serializers.ValidationError('funds and deal_size are mutually exclusive')
    if funds and funds < 0:
        raise serializers.ValidationError('funds should be greater than 0')
    if deal_size and deal_size < 0:
        raise serializers.ValidationError('deal_size should be greater than 0')

