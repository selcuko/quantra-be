from decimal import Decimal
from typing import Any
from django.core.management.base import BaseCommand, CommandParser, CommandError

from orderpulse.keeper import KeeperPool
from quantapi.models import Market, MarketSymbol

 

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        symbol_binance = MarketSymbol.objects.get(base='AVAX', market__exchange_name='OKX')
        
        keeper_futures = KeeperPool.get(symbol_binance, futures=True)
        keeper_spot = KeeperPool.get(symbol_binance)
        

        keeper_futures.start()
        keeper_spot.start()

        spot_commission = Decimal(0.001)
        futures_commission = Decimal(0.0005)
        asset_mexc = Decimal(1)
        asset_binance = Decimal(1)
        usdt_futures = Decimal(1000)
        usdt_spot = Decimal(1000)

        initial_equity = usdt_spot + usdt_futures

        last_buy_price = 0
        last_sell_price = 0

        buy_at_mexc = False
        buy_at_binance = False
        threshold = (spot_commission + futures_commission)*100

        def print_state():
            print()
            print(f'Asset MEXC: {asset_mexc:.5f}, Asset BINANCE: {asset_binance:.5f}', 'Total asset:', asset_mexc + asset_binance)
            print(f'USDT MEXC: {usdt_futures:.5f}, USDT BINANCE: {usdt_spot:.5f}', 'Total USDT:', usdt_futures + usdt_spot)
            total_equity = usdt_futures + usdt_spot + asset_mexc * last_buy_price + asset_binance * last_buy_price
            print(f'Total equity: {total_equity:.5f}')
            print(f"Investment: {initial_equity:.5f}")
            print(f"Total profit percentage: {((total_equity - initial_equity)/initial_equity)*100:.5f}%")
            print()


        old_bid = 0
        old_ask = 0
        spread = 0
        while True:
            #print('.', end='', flush=True)
            bids_futures, asks_futures = keeper_futures.book.get_best(count=5)
            bids_spot, asks_spot = keeper_spot.book.get_best(count=5)
           
            best_bid_price_futures = bids_futures[-1].price
            best_ask_price_futures = asks_futures[0].price
            best_bid_price_spot = bids_spot[-1].price
            best_ask_price_spot = asks_spot[0].price
            print(f"Spread: {spread}")
            print(f"Threshold: {threshold:.5f}")
            if  spread > threshold:
                print()
                print("Arbitrage opportunity")
                print("Futures ask price: ", best_ask_price_futures)
                print("Spot bid price: ", best_bid_price_spot)
                print("Futures bid price: ", best_bid_price_futures)
                print("Spot ask price: ", best_ask_price_spot)
                print("Spread: ", spread)
                
                print(f"Old ask , New Ask: {old_ask:.5f}, {best_ask_price_futures:.5f}")
                print(f"Old bid , New Bid: {old_bid:.5f}, {best_bid_price_spot:.5f}")
                print(f"Future change: {((best_ask_price_futures - old_ask)/old_ask)*100:.5f}%")
                print(f"Spot change: {((best_bid_price_spot - old_bid)/old_bid)*100:.5f}%")
                # Print after commission (for 1 asset trade) to changes
                
                print(f"Future change after commission: {futures_change*100:.6f}%")
                print(f"Spot change after commission: {spot_change*100:.6f}%")
                # print(f"Difference: {futures_change + spot_change:.5f}")


                print()
            old_ask = best_ask_price_futures
            old_bid = best_bid_price_spot
            spot_change = ((best_bid_price_spot - old_bid)*(1-spot_commission)/old_bid)
            print(f"Spot change: ({best_bid_price_spot - old_bid})")
            futures_change = ((old_ask - best_ask_price_futures)*(1-futures_commission)/old_ask)
            spread = (spot_change + futures_change)*100


            # if initial_equity == 2000:
            #     initial_equity += best_ask_price_spot + best_ask_price_futures

            # mexc_binance_spread = (best_ask_price_futures - best_bid_price_spot)*100/max(best_ask_price_futures, best_bid_price_spot)
            # binance_mexc_spread = (best_ask_price_spot - best_bid_price_futures)*100/max(best_ask_price_spot, best_bid_price_futures)

            
            # if  mexc_binance_spread > threshold and buy_at_binance == False and usdt_spot > 0:
            #     buy_at_binance = True
            #     buy_at_mexc = False
            #     last_buy_price = best_bid_price_spot
            #     last_sell_price = best_ask_price_futures
            #     usdt_futures += (1 - commission) * last_sell_price
            #     usdt_spot -= (1 + commission) * last_buy_price
            #     asset_mexc -= 1
            #     asset_binance += 1

            #     print_state()
               

            # elif binance_mexc_spread > threshold and buy_at_mexc == False and usdt_futures > 0:
            #     buy_at_binance = False
            #     buy_at_mexc = True
            #     last_buy_price = best_bid_price_futures
            #     last_sell_price = best_ask_price_spot
            #     usdt_spot += (1 - commission) * last_sell_price
            #     usdt_futures -= (1 + commission) * last_buy_price 
            #     asset_mexc += 1
            #     asset_binance -= 1
            #     print_state()
                
        keeper_spot.stop()
        keeper_futures.stop()

        


        