import typing
if typing.TYPE_CHECKING:
    from loops import LiveLoop
    from loops import LoopGroup


LIVELOOPS:dict[int, 'LiveLoop']  = {}
LOOPGROUPS:dict[int, 'LoopGroup'] = {}


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
