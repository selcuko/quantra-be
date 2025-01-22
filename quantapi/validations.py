from quantapi.models import Market, MarketSymbol


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
