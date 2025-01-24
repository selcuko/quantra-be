import json
import os
from django.core.management.base import BaseCommand, CommandError
from sqlalchemy import desc
from coingecko import CoinGecko
from metrichub import prepare_symbol, update_symbol
from quantapi.models import GlobalSymbol, Tag


class Command(BaseCommand):
    help = 'Create Tag objects from CoinGecko Categories'

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        cg = CoinGecko()
        categories = cg.categories()
        tags_bulk = []
        for category in categories:
            tag = Tag(
                name=category['id'],
                display=category['name'],
                description=category['content'],
                volume=category['volume_24h'],
                market_cap=category['market_cap'],
                market_cap_change_24h=category['market_cap_change_24h'],
                data_updated=category['updated_at'],
                top_3_coin_ids=",".join(category["top_3_coins_id"])
            )
            tags_bulk.append(tag)
        Tag.objects.bulk_create(tags_bulk, update_conflicts=True, unique_fields=['name'], update_fields=[
            'volume', 'market_cap', 'market_cap_change_24h', 'data_updated', 'top_3_coin_ids'
        ])
