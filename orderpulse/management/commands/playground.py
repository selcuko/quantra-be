
from django.core.management.base import BaseCommand
from django.db.models import Sum
from metrichub import *


class Command(BaseCommand):
    def handle(self, *args, **options):
        gs = GlobalSymbol.objects.get(cid='bitcoin')
        update_all_tags()

        for tag in Tag.objects.filter(metrics__volume__isnull=True):
            metrics = tag.metrics
            metrics.volume = GlobalSymbol.objects.filter(tags=tag).aggregate(Sum('metrics__volume'))['metrics__volume__sum']
            metrics.market_cap = GlobalSymbol.objects.filter(tags=tag).aggregate(Sum('metrics__market_cap'))['metrics__market_cap__sum']
            metrics.save()
