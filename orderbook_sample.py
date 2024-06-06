from pprint import pprint
from models import OrderBook, Bid
from decimal import Decimal

ob1 = OrderBook()
ob1.bids = {
    Decimal('1.0'): Bid(1.0, 1.0),
    Decimal('1.4'): Bid(1.4, 1.0),
    Decimal('2.0'): Bid(2.0, 2.0),
    Decimal('3.0'): Bid(3.0, 3.0),
    Decimal('4.0'): Bid(4.0, 4.0),
    Decimal('5.0'): Bid(5.0, 5.0),
    Decimal('15.0'): Bid(15.0, 5.0),
    Decimal('30.0'): Bid(30.0, 5.0),
}

ob1_l1 = ob1.group(2)
for b in ob1_l1.bids.values():
    print(b)
