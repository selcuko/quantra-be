from django.core.management.base import BaseCommand
from quantapi.models import Market


class Command(BaseCommand):
    help = 'Test command'

    def handle(self, *args, **options):
        market = Market.objects.get(exchange_name='MEXC')
        iface = market.get_interface()
        eq = iface.get_equity()
        print('Total equity: $', eq)