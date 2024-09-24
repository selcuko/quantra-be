from django.core.management.base import BaseCommand, CommandError
from metrichub import match_symbols, match_tags, update_all_coins_coingecko, update_all_tags


class Command(BaseCommand):
    help = 'Update all symbols from CoinGecko'

    def handle(self, *args, **options):
        update_all_tags()
        match_tags()
