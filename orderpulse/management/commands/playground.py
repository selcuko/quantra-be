
from django.core.management.base import BaseCommand

from metrichub import *


class Command(BaseCommand):
    def handle(self, *args, **options):
        gs = GlobalSymbol.objects.get(cid='bitcoin')
        update_symbol(gs)
