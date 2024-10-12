from django.core.management.base import BaseCommand, CommandError
from metrichub import cg_match_tags, fix_missing_images, match_symbols, match_tags, update_all_coins_coingecko, update_all_coins_coingecko_metrics, update_all_tags


class Command(BaseCommand):
    help = 'Update all symbols from CoinGecko'

    def handle(self, *args, **options):
        update_all_coins_coingecko()
        update_all_coins_coingecko_metrics()
        match_symbols()
        update_all_tags()
        # match_tags()  # migrating to CoinGecko tags
        # cg_match_tags()
        fix_missing_images()
