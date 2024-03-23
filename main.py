from pprint import pprint
import django
from models import OHLCVDataset
from strategy import get_strategy
django.setup()
from quantapi.models import Market


if __name__ == '__main__':
    market = Market.objects.get(exchange_name='KUCOIN', mainnet_enabled=True)
    print(market.config)
    interface = market.get_interface()
    print(interface.assets, interface.capital)
    #interface.place_market_order('BNBUSDT', 'buy', quantity=0.01)    
