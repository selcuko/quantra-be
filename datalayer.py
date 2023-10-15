import json
from datetime import datetime
from typing import Literal
from markets import Market
from dbops import DBOrder, DBSignal, DBSubscription, DBUser, session as db_session
from dbops import DBMarket, DBSymbol, DBSession
from models import interval_to_minutes


def is_db_model(model):
    return hasattr(model, '__tablename__')


def get_market(market:str) -> DBMarket:
    """Returns a DBMarket object from the database given it's name, raises ValueError if not found or multiple found

    Args:
        market (str): name of market

    Raises:
        ValueError: if no such market is found
        ValueError: if multiple markets are found

    Returns:
        DBMarket: the database market record
    """    
    returned_markets = db_session.query(DBMarket).filter_by(name=market).all()
    if len(returned_markets) == 1:
        return returned_markets[0]
    elif len(returned_markets) > 1:
        raise ValueError(f'Multiple markets found for {market}')
    raise ValueError(f'No such market found: {market}')


def get_symbol(symbol:str, market:"str|DBMarket") -> DBSymbol:
    """Returns a DBSymbol object from the database given it's name and market, raises ValueError if not found or multiple found

    Args:
        symbol (str): name of symbol in BASE-QUOTE format
        market (str|DBMarket): name of market or DBMarket object

    Raises:
        ValueError: if no such symbol is found
        ValueError: if multiple symbols are found

    Returns:
        DBSymbol: the database symbol record
    """    
    if not is_db_model(market):
        market = get_market(market)
    symbol = symbol.upper()
    returned_symbols = db_session.query(DBSymbol).filter(DBSymbol.name == symbol, DBSymbol.market == market).all()
    return returned_symbols[0]


def add_symbol(symbol:str, market:"str|DBMarket", check_exists=True) -> DBSymbol:
    """Adds a Symbol record to database, returns the DBSymbol object

    Args:
        symbol (str): name of symbol in BASE-QUOTE format
        market (str|DBMarket): name of market or DBMarket object
        check_exists (bool, optional): if True, raises ValueError if symbol already exists. Defaults to True.

    Raises:
        ValueError: if symbol already exists

    Returns:
        DBSymbol: the database symbol record
    """    
    if not is_db_model(market):
        market = get_market(market)
    symbol = symbol.upper()
    if check_exists:
        returned_symbols = db_session.query(DBSymbol).filter(DBSymbol.name == symbol, DBSymbol.market == market).all()
        if len(returned_symbols) == 1:
            return returned_symbols[0]
        elif len(returned_symbols) > 1:
            raise ValueError(f'Multiple symbols found for {symbol} in {market.name}')
    base, quote = symbol.split('-')
    symbol = DBSymbol(
        name=symbol,
        base=base,
        quote=quote,
        market=market
    )
    db_session.add(symbol)
    db_session.commit()
    return symbol


def add_session(symbol:"str|DBSymbol", market:"str|DBMarket", strategy:str, strategy_parameters:dict, status='ongoing', test_type='live.basic', freq='15 min', planned_shutdown:datetime=None) -> DBSession:
    """Adds a Session record to database, returns the DBSession object

    Args:
        symbol (str|DBSymbol): name of symbol or DBSymbol object
        market (str|DBMarket): name of market or DBMarket object
        test_type (str, optional): type of session, available choices [backtest, live.basic, live.sandbox, live.mainnet]. Defaults to 'live.basic'.
        freq (str, optional): frequency of klines, available choices [1 min, 3 min, 5 min, ...]. Defaults to '15 min'.

    Returns:
        DBSession: the database session record
    """    
    if not is_db_model(market):
        market = get_market(market)
    if not is_db_model(symbol):
        symbol = get_symbol(symbol, market)
    session = DBSession(
        session_type=test_type,
        freq=freq,
        symbol=symbol,
        strategy=strategy,
        strategy_parameters=json.dumps(strategy_parameters),
        status=status,
        planned_shutdown=planned_shutdown
    )
    db_session.add(session)
    db_session.commit()
    return session


def add_signal(session:int|DBSession, timestamp:datetime, side:Literal["buy", "sell"], price:float, rawrow:dict) -> DBSession:
    """Adds a Signal record to database, returns the DBSignal object
    
    Args:
        symbol (str|DBSymbol): name of symbol or DBSymbol object
        timestamp (datetime): timestamp of signal
        side (Literal["buy", "sell"]): side of signal
        price (float): price
        rawrow (dict): raw row of dataframe that generated this signal
    
    Returns:
        DBSignal: the database signal record
    """
    if not is_db_model(session):
        session = db_session.query(DBSession).filter_by(id=session).one()
    signal = DBSignal(
        session=session,
        timestamp=timestamp,
        side=side,
        price=price,
        rawrow=json.dumps(rawrow)
    )
    db_session.add(signal)
    db_session.commit()
    return signal


def add_order(signal:DBSignal, side:Literal['buy', 'sell'], size:float, quantity:float, price:float, order_type:Literal['MARKET', 'LIMIT'], status:str, timestamp:datetime) -> DBOrder:
    """Adds an Order record to database, returns the DBOrder object

    Args:
        signal (DBSignal): the signal that caused this order

    Returns:
        DBOrder: the database order record
    """    
    order = DBOrder(
        side=side,
        signal=signal,
        size=size,
        quantity=quantity,
        price=price,
        order_type=order_type,
        status=status,
        timestamp=timestamp
    )
    db_session.add(order)
    db_session.commit()
    return order


def add_user(name:str) -> DBUser:
    """Adds a User record to database, returns the DBUser object

    Args:
        name (str): name of user

    Returns:
        DBUser: the database user record
    """    
    user = DBUser(
        name=name
    )
    db_session.add(user)
    db_session.commit()
    return user


def add_subscription(user:int|DBUser, session:int|DBSession) -> DBSubscription:
    """Adds a Subscription record to database, returns the DBSubscription object

    Args:
        name (str): friendly name of subscription
        user (int | DBUser): user id or DBUser object
        session (int | DBSession): session id or DBSession object
        external_id (str): external id of subscription (e.g. telegram chat id)

    Returns:
        DBSubscription: the database subscription record
    """
    if not is_db_model(user):
        user = db_session.query(DBUser).filter_by(id=user).one()
    if not is_db_model(session):
        session = db_session.query(DBSession).filter_by(id=session).one()
    subscription = DBSubscription(
        user=user,
        session=session,
    )
    db_session.add(subscription)
    db_session.commit()
    return subscription
