from ast import Global
import json
import os
from django.core.management.base import BaseCommand, CommandError
from metrichub import match_symbols, match_symbols_full_payload, prepare_symbol, update_symbol
from quantapi.models import GlobalSymbol, MarketSymbol


class Command(BaseCommand):
    help = ''

    def add_arguments(self, parser):
        pass

    def handle_bulk(self, ms_bulk, bulk_count):
        self.stdout.write(f"BULK {bulk_count}", ending="\t")
        created = MarketSymbol.objects.bulk_update(ms_bulk, ["symbol"])
        self.stdout.write(self.style.SUCCESS(f'{created} MATCHED'))

    def handle(self, *args, **options):
        folder = 'cg-payloads'
        files =  os.listdir(folder)
        files.sort()
        ms_bulk = []
        bulk_size = 50
        bulk_count = 0
        not_found_total = []
        errors = []
        for file in files:
            self.stdout.write(f"Processing {file}", ending="\t")
            if not file.endswith('.json'):
                self.stdout.write(self.style.WARNING(f'SKIPPED'))
                continue
            try:
                with open(f'{folder}/{file}', 'r') as f:
                    payload = json.load(f)
                    to_save, not_found = match_symbols_full_payload(payload)
                    ms_bulk.extend(to_save)
                    not_found_total.extend(not_found)
                    if to_save:
                        self.stdout.write(self.style.SUCCESS(f'QUEUED {len(to_save)}'), ending=' ')
                    if not_found:
                        self.stdout.write(self.style.ERROR(f'NOT FOUND: {not_found}'))
                    else:
                        self.stdout.write('')
            except GlobalSymbol.DoesNotExist:
                errors.append(file)
                self.stdout.write(self.style.ERROR(f'GS NOT FOUND'))
            except KeyError:
                errors.append(file)
                self.stdout.write(self.style.ERROR(f'MALFORMED PAYLOAD'))
            if len(ms_bulk) >= bulk_size:
                bulk_count += 1
                self.handle_bulk(ms_bulk, bulk_count)
                ms_bulk = []
        if ms_bulk:
            bulk_count += 1
            self.handle_bulk(ms_bulk, bulk_count)
