from orderbook import BookKeeper, BookMaster
from models import Bid, OrderBook
from decimal import Decimal
import random
import django
django.setup()
from quantapi.models import Market, MarketSymbol


ob1 = OrderBook()
ob1.bids = {
    Decimal('1.0'): Bid(1.0, 1.0),
    Decimal('2.0'): Bid(2.0, 2.0),
    Decimal('3.0'): Bid(3.0, 3.0),
    Decimal('4.0'): Bid(4.0, 4.0),
    Decimal('5.0'): Bid(5.0, 5.0),
}
ob1.asks = {
    Decimal('6.0'): Bid(6.0, 6.0),
    Decimal('7.0'): Bid(7.0, 7.0),
    Decimal('8.0'): Bid(8.0, 8.0),
    Decimal('9.0'): Bid(9.0, 9.0),
    Decimal('10.0'): Bid(10.0, 10.0),
}

ob2 = OrderBook()
ob2.bids = {
    Decimal('1.0'): Bid(1.0, 1.5),
    Decimal('2.0'): Bid(2.0, 5.0),
    Decimal('3.0'): Bid(3.0, 0.1),
    Decimal('4.0'): Bid(4.0, 4.0),
    Decimal('5.0'): Bid(5.0, 5.0),
}
ob2.asks = {
    Decimal('6.0'): Bid(6.0, 6.0),
    Decimal('7.0'): Bid(7.0, 7.0),
    Decimal('8.0'): Bid(8.0, 8.0),
    Decimal('9.0'): Bid(9.0, 9.0),
    Decimal('10.0'): Bid(10.0, 10.0),
}

bybit_market = Market.objects.get(exchange_name='BYBIT')
btc_bybit = MarketSymbol.objects.get(name='BTC-USDT', market=bybit_market)
mexc_market = Market.objects.get(exchange_name='MEXC')
btc_mexc = MarketSymbol.objects.get(name='BTC-USDT', market=mexc_market)
bybit_keeper = BookKeeper(btc_bybit)
mexc_keeper = BookKeeper(btc_mexc)
master = BookMaster(btc_bybit)
master.add_keeper(bybit_keeper)
master.add_keeper(mexc_keeper)

bybit_keeper.orderbook = ob1
mexc_keeper.orderbook = ob2

print(master.orderbook.format())
master.keeper_callback(bybit_keeper, ob1)
print(master.orderbook.format())
master.keeper_callback(mexc_keeper, ob2)
print(master.orderbook.format())
