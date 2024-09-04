from celery import shared_task
from typing import TYPE_CHECKING
from orderpulse.keeper import Keeper, KeeperPool

if TYPE_CHECKING:
    from orderpulse.dispatchers import KeeperDispatch


@shared_task
def drop_connection(
    connection_id: str,
    dispatch: "KeeperDispatch",
    keeper: Keeper | None,
    drop_keeper: bool = True,
):
    """Lets the Dispatch know that a connection has been dropped."""
    print("Dropping connection", connection_id)
    if not keeper:
        print("No keeper provided, searching for it...")
        for k, v in dispatch.connections.items():
            if connection_id in v:
                keeper = k
                print("Found keeper:", keeper)
                break
    if not keeper:
        print("No keeper found for", connection_id)
        return
    __connections = dispatch.connections[keeper]
    __connections.remove(connection_id)
    if not __connections and drop_keeper:
        if keeper in dispatch.callbacks:
            print("Dropping callback for", keeper)
            del dispatch.callbacks[keeper]
        print("Dropping", keeper)
        del dispatch.connections[keeper]
        KeeperPool.pop(keeper)
    print("Connections:", dispatch.connections)
