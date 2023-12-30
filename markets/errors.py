

class SymbolNotInMarket(Exception):
    """Symbol not found in the market"""
    status = 400
    message = 'Symbol not found in this market'


class SymbolNotSupported(Exception):
    """Symbol not supported in the market"""
    status = 400
    message = 'Symbol not supported in this market'



class MarketAPIError(Exception):
    """Base class for exceptions in this module."""
    pass


class MarketAPIUnavailable(MarketAPIError):
    """Market API is unavailable"""
    status = 503
    message = 'Market API is unavailable'


class InsufficientBalance(Exception):
    """Insufficient balance"""
    status = 400
    message = 'Insufficient balance'


class KlineFetchFailed(MarketAPIError):
    """Failed to fetch kline data"""
    status = 503
    message = 'Failed to fetch kline data'


class RejectedOrder(Exception):
    """Order was rejected by the exchange"""
    status = 400
    message = 'Order was rejected by the exchange'


class NoMarketLiquidity(Exception):
    """Market has no liquidity for given pair"""
    status = 400
    message = 'Market has no liquidity for given pair, cannot place market order'


class MarketDisabledTrading(Exception):
    """Market does not support this kind of trading"""
    status = 400
    message = 'Market does not support trading'

