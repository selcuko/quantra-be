
import json
from django.core.management.base import BaseCommand

from quantapi.models import GlobalSymbol, MarketSymbol


class Command(BaseCommand):
    gs = GlobalSymbol.objects.exclude(available_markets='[]')
    count = gs.count()

    for i, symbol in enumerate(gs):
        print(f'{i}/{count}')
        ms = MarketSymbol.objects.filter(symbol=symbol)
        symbol.available_markets = json.dumps(list(ms.values_list('market__exchange_name', flat=True)))
        symbol.save()