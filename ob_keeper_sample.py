import time
from orderbook import BookKeeper


if __name__ == '__main__':
    import django
    django.setup()
    from quantapi.models import Market, MarketSymbol
    market = Market.objects.get(exchange_name='BYBIT')
    symbol = MarketSymbol.objects.get(market=market, name='BTC-USDT')
    keeper = BookKeeper(symbol)
    keeper.start()
    while True:
        try:
            print(keeper.orderbook.format())
            print(keeper.orderbook.overview())
            time.sleep(1)
        except KeyboardInterrupt:
            break
