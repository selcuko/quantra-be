from decimal import Decimal
from itertools import combinations
from typing import Any
from django.core.management.base import BaseCommand, CommandParser, CommandError

from orderpulse.keeper import KeeperPool
from quantapi.models import Market, MarketSymbol


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        symbols = [
            MarketSymbol.objects.get(contract_type=MarketSymbol.ContractType.SPOT, base='IMX', market__exchange_name='MEXC'),
            MarketSymbol.objects.get(contract_type=MarketSymbol.ContractType.SPOT, base='IMX', market__exchange_name='BINANCE'),
            MarketSymbol.objects.get(contract_type=MarketSymbol.ContractType.SPOT, base='IMX', market__exchange_name='OKX'),
            MarketSymbol.objects.get(contract_type=MarketSymbol.ContractType.SPOT, base='IMX', market__exchange_name='KUCOIN'),
            MarketSymbol.objects.get(contract_type=MarketSymbol.ContractType.SPOT, base='IMX', market__exchange_name='BYBIT'),
            MarketSymbol.objects.get(contract_type=MarketSymbol.ContractType.SPOT, base='IMX', market__exchange_name='GATEIO'),
        ]

        # Generate all unique pairs (combinations) of symbols
        symbol_pairs = list(combinations(symbols, 2))

        # Initialize keepers for all symbols
        keepers = {symbol: KeeperPool.get(symbol) for symbol in symbols}

        # Start all keepers
        for keeper in keepers.values():
            keeper.start()

        commission = Decimal(0.001)
        assets = {symbol: Decimal(1) for symbol in symbols}
        usdt_balances = {symbol: Decimal(1000) for symbol in symbols}

        initial_equity = sum(usdt_balances.values())

        def print_state(symbol_a, symbol_b, last_buy_price, last_sell_price):
            print()
            print(f'Asset {symbol_a.market.exchange_name}: {assets[symbol_a]:.5f}, '
                  f'Asset {symbol_b.market.exchange_name}: {assets[symbol_b]:.5f}')
            print(f'USDT {symbol_a.market.exchange_name}: {usdt_balances[symbol_a]:.5f}, '
                  f'USDT {symbol_b.market.exchange_name}: {usdt_balances[symbol_b]:.5f}')
            total_equity = sum(usdt_balances.values()) + assets[symbol_a] * last_buy_price + assets[symbol_b] * last_sell_price
            print(f'Total equity: {total_equity:.5f}')
            print(f"Investment: {initial_equity:.5f}")
            print(f"Total profit percentage: {((total_equity - initial_equity)/initial_equity)*100:.5f}%")
            print()

        threshold = Decimal(0.15)  # Adjust as needed
        while True:
            print('.', end='', flush=True)

            for symbol_a, symbol_b in symbol_pairs:
                bids_a, asks_a = keepers[symbol_a].book.get_best(count=5)
                bids_b, asks_b = keepers[symbol_b].book.get_best(count=5)

                best_bid_price_a = bids_a[-1].price
                best_ask_price_a = asks_a[0].price
                best_bid_price_b = bids_b[-1].price
                best_ask_price_b = asks_b[0].price

                spread_a_b = (best_ask_price_a - best_bid_price_b) * 100 / max(best_ask_price_a, best_bid_price_b)
                spread_b_a = (best_ask_price_b - best_bid_price_a) * 100 / max(best_ask_price_b, best_bid_price_a)

                # Execute trades based on the spread
                if spread_a_b > threshold and usdt_balances[symbol_b] > 0:
                    last_buy_price = best_bid_price_b
                    last_sell_price = best_ask_price_a
                    usdt_balances[symbol_a] += (1 - commission) * last_sell_price
                    usdt_balances[symbol_b] -= (1 + commission) * last_buy_price
                    assets[symbol_a] -= 1
                    assets[symbol_b] += 1

                    print_state(symbol_a, symbol_b, last_buy_price, last_sell_price)

                elif spread_b_a > threshold and usdt_balances[symbol_a] > 0:
                    last_buy_price = best_bid_price_a
                    last_sell_price = best_ask_price_b
                    usdt_balances[symbol_b] += (1 - commission) * last_sell_price
                    usdt_balances[symbol_a] -= (1 + commission) * last_buy_price
                    assets[symbol_a] += 1
                    assets[symbol_b] -= 1

                    print_state(symbol_b, symbol_a, last_buy_price, last_sell_price)

        # Stop all keepers
        for keeper in keepers.values():
            keeper.stop()
