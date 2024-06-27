

class SymbolNotInMarket(Exception):
    """Symbol not found in the market"""
    status_code = 400
    message = 'Symbol not found in this market'


class SymbolNotSupported(Exception):
    """Symbol not supported in the market"""
    status_code = 400
    message = 'Symbol not supported in this market'


class OrderPostProcessingError(Exception):
    """Error during order post-processing"""
    status_code = 500
    message = 'Error during order post-processing. Order might be placed, but not confirmed.'

    def __init__(self, message=None, oid=None):
        self.message = message or self.message
        self.oid = oid


class OrderValidationError(Exception):
    """Error during order validation"""
    status_code = 500
    message = 'Error during order validation'


class OrderNotFilledError(Exception):
    """Order was not filled"""
    status_code = 503
    message = 'Order was not filled'

    def __init__(self, message:str, order):
        self.message = message or self.message
        self.order = order


class MarketAPIError(Exception):
    """Base class for exceptions in this module."""
    pass


class MarketAPIUnavailable(MarketAPIError):
    """Market API is unavailable"""
    status_code = 503
    message = 'Market API is unavailable'


class InsufficientBalance(Exception):
    """Insufficient balance"""
    status_code = 400
    message = 'Insufficient balance'


class KlineFetchFailed(MarketAPIError):
    """Failed to fetch kline data"""
    status_code = 503
    message = 'Failed to fetch kline data'


class RejectedOrder(Exception):
    """Order was rejected by the exchange"""
    status_code = 400
    message = 'Order was rejected by the exchange'


class NoMarketLiquidity(Exception):
    """Market has no liquidity for given pair"""
    status_code = 400
    message = 'Market has no liquidity for given pair, cannot place market order'


class MarketDisabledTrading(Exception):
    """Market does not support this kind of trading"""
    status_code = 400
    message = 'Market does not support trading'


class OrderPlacementError(Exception):
    """Error placing order"""
    status_code = 500
    message = 'Error placing order'