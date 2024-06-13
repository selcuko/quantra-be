from quantapi.models import Session


def can_session_buy(session: Session):
    return session.capital > 5


def can_session_sell(session: Session):
    return session.assets > 0
