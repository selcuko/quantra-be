


from orderpulse.keeper import BookKeeper
from quantapi.models import MarketSymbol


class Consolidator:
    def __init__(self, symbol: MarketSymbol):
        self.keepers = {}
        self.symbol = symbol

    def add_keeper(self, keeper: BookKeeper):
        if not keeper.symbol.name == self.symbol.name:
            raise ValueError(f'Keeper {keeper.symbol.name} does not match Consolidator {self.symbol.name}')
        if not keeper.is_running():
            keeper.start()
        self.keepers[keeper.account.market.exchange_name] = keeper

