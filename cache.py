import typing
if typing.TYPE_CHECKING:
    from loops import LiveLoop
    from loops import LoopGroup
    from quantapi.models import Market, IMarket


LIVELOOPS:dict[int, 'LiveLoop']  = {}
LOOPGROUPS:dict[int, 'LoopGroup'] = {}
INTERFACES:dict['Market', 'IMarket'] = {}


def get_liveloop(session_id:int) -> 'LiveLoop|None':
    return LIVELOOPS.get(session_id)


def set_liveloop(session_id:int, liveloop:'LiveLoop') -> None:
    global LIVELOOPS
    LIVELOOPS[session_id] = liveloop


def del_liveloop(session_id:int) -> None:
    global LIVELOOPS
    del LIVELOOPS[session_id]


def get_loopgroup(group_id:int) -> 'LoopGroup|None':
    return LOOPGROUPS.get(group_id)


def set_loopgroup(group_id:int, loopgroup:'LoopGroup') -> None:
    global LOOPGROUPS
    LOOPGROUPS[group_id] = loopgroup


def del_loopgroup(group_id:int) -> None:
    global LOOPGROUPS
    del LOOPGROUPS[group_id]

def set_interface(market:'Market', iface:'IMarket') -> None:
    global INTERFACES
    INTERFACES[market] = iface

def get_interface(market:'Market') -> 'IMarket|None':
    return INTERFACES.get(market)

def del_interface(market:'Market') -> None:
    global INTERFACES
    del INTERFACES[market]
