import json
import os
from django.core.management.base import BaseCommand, CommandError
from metrichub import prepare_symbol, update_symbol
from quantapi.models import GlobalSymbol


class Command(BaseCommand):
    help = 'Create GlobalSymbol objects from CoinGecko payloads'

    def add_arguments(self, parser):
        parser.add_argument(
            '--update',
            action='store_true',
            default=False,
            help='Update existing GlobalSymbols',
        )

    def handle_bulk(self, gs_bulk, bulk_count):
        self.stdout.write(f"BULK {bulk_count}", ending="\t")
        created = GlobalSymbol.objects.bulk_create(gs_bulk, ignore_conflicts=True)
        self.stdout.write(self.style.SUCCESS(f'{len(created)} CREATED'))

    def handle(self, *args, **options):
        folder = 'cg-payloads'
        files = os.listdir(folder)
        cids = [f.split('.')[0] for f in files]
        existing_gs = GlobalSymbol.objects.filter(cid__in=cids)
        existing = existing_gs.values_list('cid', flat=True)
        files.sort()
        gs_bulk = []
        bulk_size = 10
        bulk_count = 0
        errors = []
        for file in files:
            gs = None
            self.stdout.write(f"Processing {file}", ending="\t")
            if not file.endswith('.json'):
                self.stdout.write(self.style.WARNING(f'SKIPPED'))
                continue
            if file.split('.')[0] in existing:
                if options.get('update'):
                    gs = existing_gs.get(cid=file.split('.')[0])
                else:
                    self.stdout.write(self.style.WARNING(f'ALREADY EXISTS'))
                    continue
            with open(f'{folder}/{file}', 'r') as f:
                try:
                    payload = json.load(f)
                    if not gs:
                        gs = prepare_symbol(payload)
                    gs = update_symbol(gs, payload, match=False, save=False)
                    gs_bulk.append(gs)
                    self.stdout.write(self.style.SUCCESS(f'QUEUED'))
                except KeyboardInterrupt:
                    self.stdout.write(self.style.ERROR(f'INTERRUPTED'))
                    break
                except Exception as e:
                    errors.append(file)
                    self.stdout.write(self.style.ERROR(f'ERROR: {e}'))
            if len(gs_bulk) >= bulk_size:
                bulk_count += 1
                self.handle_bulk(gs_bulk, bulk_count)
                gs_bulk = []
        if gs_bulk:
            bulk_count += 1
            self.handle_bulk(gs_bulk, bulk_count)
        if errors:
            self.stdout.write(self.style.ERROR(f'We had some issues with: {errors}'))
