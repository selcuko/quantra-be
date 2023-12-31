from pprint import pprint
import django
django.setup()
from quantapi.models import Market


if __name__ == '__main__':
    market = Market.objects.get(exchange_name='MEXC')
    interface = market.get_interface()
    pprint(interface.assets)
    """response = interface.place_market_order(
        'MX-USDT', 'buy', funds=200, validate=True
    )"""
    response = interface.get_order('MX-USDT', 'C01__000000000000000000')
    print(response)
