from django.core.management.base import BaseCommand, CommandError
from metrichub import match_symbols, update_all_coins_coingecko


class Command(BaseCommand):
    help = 'Update all symbols from CoinGecko'

    def handle(self, *args, **options):
        update_all_coins_coingecko()
        match_symbols()
