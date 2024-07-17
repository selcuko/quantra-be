

class NoEquityError(Exception):
    '''Raised when there is no meaningful equity left in the Session or SessionGroup (i.e. ghost state)'''
    pass


class AlreadyRunningError(Exception):
    '''Raised when trying to start a Session or SessionGroup that is already running'''
    message = 'This Loop is already running.'


class CannotFetchCandles(Exception):
    '''Raised when the interface cannot fetch candles for some reason'''
    pass

