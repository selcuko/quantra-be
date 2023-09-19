

from typing import Literal


class PriceFilter:
    def __init__(self, **kwargs) -> None:
        self.ask_multiplier_down: float = kwargs.get('ask_multiplier_down')
        self.ask_multiplier_up: float = kwargs.get('ask_multiplier_up')
        self.bid_multiplier_down: float = kwargs.get('bid_multiplier_down')
        self.bid_multiplier_up: float = kwargs.get('bid_multiplier_up')
        self.max_price: float = kwargs.get('max_price')
        self.min_price: float = kwargs.get('min_price')
        self.tick_size: float = kwargs.get('tick_size')

    def round(self, price:float) -> float:
        if not self.tick_size:
            return price
        if not float(self.tick_size):
            return price
        return (price // float(self.tick_size)) * float(self.tick_size)
    
    def validate(self, price:float, side:Literal['buy', 'sell']):
        # Price filters
        if self.max_price and price > float(self.max_price):
            raise ValueError(f'Price {price} is too high, maximum is {self.max_price}')
        if self.min_price and price < float(self.min_price):
            raise ValueError(f'Price {price} is too low, minimum is {self.min_price}')
        if self.tick_size and float(self.tick_size) > 0 and price % float(self.tick_size) != 0:
            raise ValueError(f'Price {price} is not a multiple of {self.tick_size}')
        
        # Percent price filters
        if side == 'buy' and self.ask_multiplier_up and price > float(self.ask_multiplier_up):
            raise ValueError(f'Price {price} is too high, maximum is {self.ask_multiplier_up}')
        if side == 'buy' and self.ask_multiplier_down and price < float(self.ask_multiplier_down):
            raise ValueError(f'Price {price} is too low, minimum is {self.ask_multiplier_down}')
        if side == 'sell' and self.bid_multiplier_up and price > float(self.bid_multiplier_up):
            raise ValueError(f'Price {price} is too high, maximum is {self.bid_multiplier_up}')
        if side == 'sell' and self.bid_multiplier_down and price < float(self.bid_multiplier_down):
            raise ValueError(f'Price {price} is too low, minimum is {self.bid_multiplier_down}')
        return True
            
 
class LotFilter:
    def __init__(self, **kwargs) -> None:
        self.minimum_quantity: float = kwargs.get('min_qty')
        self.maximum_quantity: float = kwargs.get('max_qty')
        self.step_size: float = kwargs.get('step_size')
        self.applies_to_market: bool = kwargs.get('apply_to_market', True)
    
    def round(self, quantity:float) -> float:
        if not self.step_size:
            return quantity
        if not float(self.step_size):
            return quantity
        return (quantity // float(self.step_size)) * float(self.step_size)
    
    def validate(self, quantity:float, order_type:Literal['limit', 'market']):
        if not self.applies_to_market and order_type == 'market':
            return True
        if self.minimum_quantity and quantity < float(self.minimum_quantity):
            raise ValueError(f'Quantity {quantity} is too low, minimum is {self.minimum_quantity}')
        if self.maximum_quantity and quantity > float(self.maximum_quantity):
            raise ValueError(f'Quantity {quantity} is too high, maximum is {self.maximum_quantity}')
        if self.step_size and float(self.step_size) > 0 and quantity % float(self.step_size) != 0:
            raise ValueError(f'Quantity {quantity} is not a multiple of {self.step_size}')
        return True
    

class FundFilter:
    def __init__(self, **kwargs) -> None:
        self.minimum_notional: float = kwargs.get('min_notional')
        self.maximum_notional: float = kwargs.get('max_notional')
        self.applies_to_market: bool = kwargs.get('apply_to_market', True)
        self.applies_min_to_market: bool = kwargs.get('apply_min_to_market', self.applies_to_market)
        self.applies_max_to_market: bool = kwargs.get('apply_max_to_market', self.applies_to_market)
    
    def validate(self, funds:float, order_type:Literal['limit', 'market']):
        if not self.applies_to_market and order_type == 'market':
            return True
        if self.applies_min_to_market and self.minimum_notional and funds < float(self.minimum_notional):
            raise ValueError(f'Funds {funds} is too low, minimum is {self.minimum_notional}')
        if self.applies_max_to_market and self.maximum_notional and funds > float(self.maximum_notional):
            raise ValueError(f'Funds {funds} is too high, maximum is {self.maximum_notional}')
        return True

