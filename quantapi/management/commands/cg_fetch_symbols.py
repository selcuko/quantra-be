import json
import os
from textwrap import indent
import time
from django.core.management.base import BaseCommand, CommandError
from quantapi.models import GlobalSymbol
from coingecko import CoinGecko


class Command(BaseCommand):

    def add_arguments(self, parser):
        output = parser.add_argument("--output", type=str, help="Output dir path", default="cg-payloads")

    def handle(self, *args, **options):
        symbols = GlobalSymbol.objects.prefetch_related('symbols__market').filter(symbols__isnull=False).distinct()
        cg = CoinGecko()
        if not os.path.exists(options['output']):
            os.makedirs(options['output'])
        for s in symbols:
            print(f'Fetching {s.base} ({s.cid})', end='\t', flush=True)
            if os.path.exists(f"{options['output']}/{s.cid}.json"):
                print('Already fetched', flush=True)
                continue
            payload = cg.coin_by_cid(s.cid)
            with open(f"{options['output']}/{s.cid}.json", 'w') as f:
                f.write(json.dumps(payload, indent=4))
            print('OK', flush=True)
            time.sleep(2)
