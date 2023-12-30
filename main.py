from pprint import pprint
import django
django.setup()
from quantapi.models import Market


if __name__ == '__main__':
    market = Market.objects.get(exchange_name='MEXC')
    interface = market.get_interface()
    response = interface.place_market_order(
        'MX-USDT',
        'buy',
        5
    )
    print(response)
