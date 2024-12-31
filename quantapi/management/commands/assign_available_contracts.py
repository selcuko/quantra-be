from django.core.management.base import BaseCommand

from quantapi.models import MarketSymbol


class Command(BaseCommand):
    def handle(self, *args, **options):
        symbols = MarketSymbol.objects.prefetch_related('market').all()
        count = symbols.count()
        for i, symbol in enumerate(symbols):
            print(f"[{i}/{count}]", symbol.base, end='\t')
            contracts = symbol.market.symbols.filter(name=symbol.name).values_list('contract_type', flat=True)
            symbol.available_contracts = ','.join(contracts)
            print(symbol.available_contracts)
        updated = MarketSymbol.objects.bulk_update(symbols, ['available_contracts'])
        print(f'Updated {updated} MarketSymbols')
