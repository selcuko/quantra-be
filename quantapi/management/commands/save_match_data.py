import os
from django.core.management.base import BaseCommand, CommandParser, CommandError
from liveloop import LiveLoop
from markets.errors import MarketAPIUnavailable
from quantapi.models import MarketAccount


class MockLiveLoop(LiveLoop):
    def __init__(self, *args, **kwargs):
        self.__stop = False

    def should_stop(self):
        return self.__stop

class Command(BaseCommand):
    help = 'Save MatchEngine data to a CSV file'

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument('--symbol', type=str, help='Trading pair symbol (e.g. BTC-USDT)')
        parser.add_argument('--market', type=str, help='Market exchange name (e.g. MEXC)')
        parser.add_argument('--output', type=str, help='Output file path')
        parser.add_argument('--overwrite', action='store_true', help='Overwrite output file if it exists')

    def handle(self, *args, **options):
        self.options = options
        self.prep_file()
        try:
            iface = MarketAccount.objects.get(market__exchange_name=self.options['market'].upper()).get_interface()
        except MarketAccount.DoesNotExist:
            raise CommandError(f'Market account for {self.options["market"]} not found')
        except MarketAPIUnavailable:
            raise CommandError(f'Market API for {self.options["market"]} is unavailable')
        symbol = self.options['symbol'].lower().replace('-', '').replace('usdt', '').upper() + '-USDT'
        try:
            mll = MockLiveLoop()
            iface.init_match_engine(symbol, '1 min', self.on_candle, mll)
            mll.__stop = True
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS('Exiting...'))
        except Exception as e:
            raise CommandError(f'Error initializing match engine: {e}')

    def prep_file(self):
        if not self.options['output'].endswith('.csv'):
            self.stdout.write(self.style.WARNING('Output format is CSV but provided output file does not have a .csv extension.'))
        if os.path.exists(self.options['output']):
            if self.options.get('overwrite'):
                self.stdout.write(self.style.WARNING('Output file already exists. Overwriting...'))
            else:
                raise CommandError('Output file already exists. Use --overwrite to overwrite the file.')
        with open(self.options['output'], 'w') as f:
            f.write('time,open,high,low,volume,start,end,buy_vol,buy_count,close,sell_vol,sell_count,corrupt\n')

    def on_candle(self, candle: dict):
        self.stdout.write(f'Writing candle [{candle["time"]}]', ending='\t')
        try:
            with open(self.options['output'], 'a') as f:
                f.write(f'{self.format_candle(candle)}\n')
            self.stdout.write(self.style.SUCCESS('OK'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error writing candle: {e}'))

    def format_candle(self, candle):
        return f'{candle["time"].timestamp()},{candle["open"]},{candle["high"]},{candle["low"]},{candle["volume"]},{candle["start"].timestamp()},{candle["end"].timestamp()},{candle["buy_vol"]},{candle["buy_count"]},{candle["close"]},{candle["sell_vol"]},{candle["sell_count"]},{int(candle["corrupt"])}'
