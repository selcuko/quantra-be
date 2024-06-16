from quantapi.models import Session, SessionGroup


def can_group_buy(group: SessionGroup):
    return group.buy_enabled


def can_group_sell(group: SessionGroup):
    return group.sell_enabled


def can_session_buy(session: Session):
    group_enabled = can_group_buy(session.group) if session.group else True
    return session.capital > 5 and session.buy_enabled and group_enabled


def can_session_sell(session: Session):
    group_enabled = can_group_sell(session.group) if session.group else True
    return session.assets > 0 and session.sell_enabled and group_enabled
