from decimal import Decimal
from typing import Any
from django.core.management.base import BaseCommand, CommandParser, CommandError

from orderpulse.keeper import KeeperPool
from quantapi.models import Market, MarketSymbol

 

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        symbol_mexc = MarketSymbol.objects.get(contract_type=MarketSymbol.ContractType.SPOT, base='AVAX', market__exchange_name='BYBIT')
        symbol_binance = MarketSymbol.objects.get(contract_type=MarketSymbol.ContractType.SPOT, base='AVAX', market__exchange_name='OKX')
        
        keeper_mexc = KeeperPool.get(symbol_mexc)
        keeper_binance = KeeperPool.get(symbol_binance)
        

        keeper_mexc.start()
        keeper_binance.start()

        commission = Decimal(0.001)
        asset_mexc = Decimal(1)
        asset_binance = Decimal(1)
        usdt_mexc = Decimal(1000)
        usdt_binance = Decimal(1000)

        initial_equity = usdt_binance + usdt_mexc

        last_buy_price = 0
        last_sell_price = 0

        buy_at_mexc = False
        buy_at_binance = False
        threshold = Decimal(0.11) 

        def print_state():
            print()
            print(f'Asset MEXC: {asset_mexc:.5f}, Asset BINANCE: {asset_binance:.5f}', 'Total asset:', asset_mexc + asset_binance)
            print(f'USDT MEXC: {usdt_mexc:.5f}, USDT BINANCE: {usdt_binance:.5f}', 'Total USDT:', usdt_mexc + usdt_binance)
            total_equity = usdt_mexc + usdt_binance + asset_mexc * last_buy_price + asset_binance * last_buy_price
            print(f'Total equity: {total_equity:.5f}')
            print(f"Investment: {initial_equity:.5f}")
            print(f"Total profit percentage: {((total_equity - initial_equity)/initial_equity)*100:.5f}%")
            print()

        while True:
            print('.', end='', flush=True)
            bids_mexc, asks_mexc = keeper_mexc.book.get_best(count=5)
            bids_binance, asks_binance = keeper_binance.book.get_best(count=5)
           
            best_bid_price_mexc = bids_mexc[-1].price
            best_ask_price_mexc = asks_mexc[0].price
            best_bid_price_binance = bids_binance[-1].price
            best_ask_price_binance = asks_binance[0].price


            if initial_equity == 2000:
                initial_equity += best_ask_price_binance + best_ask_price_mexc

            mexc_binance_spread = (best_ask_price_mexc - best_bid_price_binance)*100/max(best_ask_price_mexc, best_bid_price_binance)
            binance_mexc_spread = (best_ask_price_binance - best_bid_price_mexc)*100/max(best_ask_price_binance, best_bid_price_mexc)

            
            if  mexc_binance_spread > threshold and buy_at_binance == False and usdt_binance > 0:
                buy_at_binance = True
                buy_at_mexc = False
                last_buy_price = best_bid_price_binance
                last_sell_price = best_ask_price_mexc
                usdt_mexc += (1 - commission) * last_sell_price
                usdt_binance -= (1 + commission) * last_buy_price
                asset_mexc -= 1
                asset_binance += 1

                print_state()
               

            elif binance_mexc_spread > threshold and buy_at_mexc == False and usdt_mexc > 0:
                buy_at_binance = False
                buy_at_mexc = True
                last_buy_price = best_bid_price_mexc
                last_sell_price = best_ask_price_binance
                usdt_binance += (1 - commission) * last_sell_price
                usdt_mexc -= (1 + commission) * last_buy_price 
                asset_mexc += 1
                asset_binance -= 1
                print_state()
                
        keeper_binance.stop()
        keeper_mexc.stop()

        


        