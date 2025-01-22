from django.core.management.base import BaseCommand, CommandError
from quantapi.models import Market


class Command(BaseCommand):
    help = 'Reload Market objects to populate MarketSymbols, market prices, etc.'

    def add_arguments(self, parser):
        parser.add_argument('--markets', type=str, nargs='*', default=None)

    def handle(self, *args, **options):
        if options.get('markets'):
            markets = Market.objects.filter(exchange_name__in=[market.upper() for market in options['markets']])
        else:
            markets = Market.objects.all()
            self.stdout.write(f'Found {markets.count()} markets: {", ".join([market.display_name for market in markets])}')

        for market in markets:
            self.stdout.write(f'Reloading {market.display_name}...', ending="\t")
            try:
                iface = market.get_interface()
                iface.get_current_prices()
            except:
                self.stdout.write(self.style.ERROR("ERROR"))
                continue
            self.stdout.write(self.style.SUCCESS("OK"))

