import json
import os
from django.core.management.base import BaseCommand, CommandParser, CommandError
from django.utils import timezone
from liveloop import LiveLoop
from markets.errors import MarketAPIUnavailable
from quantapi.models import MarketAccount


class MockLiveLoop(LiveLoop):
    def __init__(self, *args, **kwargs):
        self.__stop = False

    def should_stop(self):
        return self.__stop

class Command(BaseCommand):
    help = 'Save raw execution data to a JSON file'

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument('--symbol', required=True, type=str, help='Trading pair symbol (e.g. BTC-USDT)')
        parser.add_argument('--market', required=True, type=str, help='Market exchange name (e.g. MEXC)')
        parser.add_argument('--output', required=True, type=str, help='Output file path')
        parser.add_argument('--overwrite', action='store_true', help='Overwrite output file if it exists')

    def handle(self, *args, **options):
        self.options = options
        self.counter = 0
        self.prep_file()
        try:
            iface = MarketAccount.objects.filter(market__exchange_name=self.options['market'].upper()).first()
            if not iface:
                raise MarketAccount.DoesNotExist
            iface = iface.get_interface()
        except MarketAccount.DoesNotExist:
            raise CommandError(f'Market account for {self.options["market"]} not found')
        except MarketAPIUnavailable:
            raise CommandError(f'Market API for {self.options["market"]} is unavailable')
        symbol = self.options['symbol'].lower().replace('-', '').replace('usdt', '').upper() + '-USDT'
        try:
            mll = MockLiveLoop()
            iface.init_match_engine(symbol, '1 min', lambda x:x, mll, self.on_candle)
            mll.__stop = True
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS('Exiting...'))
        except Exception as e:
            raise CommandError(f'Error initializing match engine: {e!r}')

    def prep_file(self):
        if not self.options['output'].endswith('.json'):
            self.stdout.write(self.style.WARNING('Output format is JSON but provided output file does not have a .json extension.'))
        if os.path.exists(self.options['output']):
            if self.options.get('overwrite'):
                self.stdout.write(self.style.WARNING('Output file already exists. Overwriting...'))
            else:
                raise CommandError('Output file already exists. Use --overwrite to overwrite the file.')
        with open(self.options['output'], 'w') as f:
            payload = {
                'symbol': self.options['symbol'],
                'market': self.options['market'],
            }
            f.write(f'{json.dumps(payload)}\n')

    def on_candle(self, candle: dict):
        if not self.counter:
            self.counter = 0
        self.counter += 1
        self.stdout.write(f'[{timezone.now()}]', ending='\t')
        try:
            with open(self.options['output'], 'a') as f:
                f.write(f'{json.dumps(candle)}\n')
                self.stdout.write(self.style.SUCCESS('OK'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error writing candle: {e}'))

    
