from rest_framework import serializers

from quantapi.models import Market, MarketSymbol, Session


def validate_symbol_against_market(symbol: MarketSymbol, market: Market) -> bool:
    """
    Validate that the symbol can be used for a Session.
    """
    if not symbol or not symbol.pk:
        raise Exception('Symbol is required')
    if not market or not market.pk:
        raise Exception('Market is required')
    if symbol.market != market:
        raise Exception(f'Symbol\'s market {symbol.market.exchange_name} does not match the market {market.exchange_name}')
    if not symbol.spot_trading_enabled:
        raise Exception(f'Spot trading is not enabled for {symbol.base} in {market.exchange_name}')
    return True


def validate_session_can_start(session: Session):
    """
    Validate that the session can start.
    """
    if not session or not session.pk:
        raise Exception('Session is required')
    if session.status not in [Session.Status.PLANNED, Session.Status.PAUSED]:
        raise Exception(f'Session is not in a state that can be started: {session.status}')
    if session.equity < 5:
        raise Exception(f'Session equity (${session.equity}) is too low to start trading (minimum is $5)')
    return True