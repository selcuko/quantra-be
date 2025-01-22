import json
import os
from django.core.management.base import BaseCommand, CommandError
from metrichub import update_symbol


class Command(BaseCommand):
    help = ''

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        folder = 'cg-payloads'
        files = os.listdir(folder)
        files.sort()
        for file in files:
            if not file.endswith('.json'):
                self.stdout.write(self.style.WARNING(f'Skipping {file}'))
            with open(f'{folder}/{file}', 'r') as f:
                payload = json.load(f)
                update_symbol(payload)
