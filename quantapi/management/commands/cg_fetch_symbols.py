import json
import os
from textwrap import indent
import time
from django.core.management.base import BaseCommand, CommandError
from quantapi.models import GlobalSymbol
from coingecko import CoinGecko


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument("--output", type=str, help="Output dir path", default="cg-payloads")

    def handle(self, *args, **options):
        cg = CoinGecko()
        if not os.path.exists(options['output']):
            os.makedirs(options['output'])
        previously_existing = []
        newly_saved = []
        for s in cg.coins:
            self.stdout.write(f'Fetching {s["id"]}', ending='\t')
            if os.path.exists(f"{options['output']}/{s['id']}.json"):
                self.stdout.write(self.style.WARNING('ALREADY EXISTS'))
                previously_existing.append(s)
                continue
            payload = cg.coin_by_cid(s["id"])
            with open(f"{options['output']}/{s['id']}.json", 'w') as f:
                f.write(json.dumps(payload, indent=4))
            newly_saved.append(s)
            self.stdout.write(self.style.SUCCESS('DONE'))
            #time.sleep(2)
        self.stdout.write(f'Newly saved: {len(newly_saved)}')
        self.stdout.write(f'Previously existing: {len(previously_existing)}')
