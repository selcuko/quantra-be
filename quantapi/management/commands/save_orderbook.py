from decimal import Decimal
import json
import os
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from liveloop import LiveLoop
from quantapi.models import Market, MarketAccount, MarketSymbol


class MockLiveLoop(LiveLoop):
    def __init__(self, *args, **kwargs):
        self.__stop = False

    def should_stop(self):
        return self.__stop


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


class Command(BaseCommand):
    help = 'Start saving realtime orderbook data and continue indefinitely.'

    def add_arguments(self, parser: CommandParser):
        parser.add_argument('--symbol', required=True, type=str, help='Name of the trading pair (e.g. BTC-USDT)')
        parser.add_argument('--market', required=True, type=str, help='Name of the exchange (e.g. BINANCE)')
        parser.add_argument('--account', required=False, type=str, help='Optional MarketAccount ID to be used as the interface')
        parser.add_argument('--output', required=True, type=str, help='Output file path')
        parser.add_argument('--overwrite', action='store_true', help='Overwrite the file if it already exists')

    def handle(self, *args, **options):
        self.options = options
        try:
            self.market = Market.objects.get(exchange_name=self.options['market'].upper())
        except Market.DoesNotExist:
            raise CommandError(f'Market {self.options["market"]} not found.')
        try:
            symbol = self.options['symbol'].lower().replace('-', '').replace('usdt', '').upper()
            self.symbol = MarketSymbol.objects.get(market=self.market, base=symbol)
        except MarketSymbol.DoesNotExist:
            raise CommandError(f'Symbol {symbol} not found in {self.market.exchange_name}.')
        if self.options.get('account'):
            try:
                self.account = MarketAccount.objects.get(id=self.options['account'])
            except MarketAccount.DoesNotExist:
                raise CommandError(f'MarketAccount ID={self.options["account"]} not found.')
            if self.account.market != self.market:
                raise CommandError(f'MarketAccount ID={self.options["account"]} does not belong to {self.market.exchange_name}.')
        else:
            self.account = MarketAccount.objects.filter(market=self.market).first()
            if not self.account:
                raise CommandError(f'No MarketAccount found for {self.market.exchange_name}.')
        self.prep_file()
        self.interface = self.account.get_interface()
        self.prep_snapshot()
        self.interface.init_orderbook_websocket(
            self.symbol,
            self.on_update,
            MockLiveLoop()
        )

    def prep_file(self):
        if not self.options['output'].endswith('.json'):
            self.stdout.write(self.style.WARNING('Output format is JSON but provided output file does not have a .json extension.'))
        if os.path.exists(self.options['output']):
            if self.options.get('overwrite'):
                self.stdout.write(self.style.WARNING('Output file already exists. Overwriting...'))
            else:
                raise CommandError('Output file already exists. Use --overwrite to overwrite the file.')
        with open(self.options['output'], 'w') as f:
            header_payload = {
                'start': timezone.now().timestamp(),
                'symbol': {
                    'name': self.symbol.name,
                    'id': self.symbol.pk,
                },
                'market': self.market.exchange_name,
                'account.id': self.account.pk if self.account else None, 
            }
            f.write(json.dumps(header_payload) + '\n')

    def prep_snapshot(self):
        full_ob = self.interface.get_full_orderbook(self.symbol)
        with open(self.options['output'], 'a') as f:
            f.write(json.dumps(full_ob, cls=DecimalEncoder) + '\n')

    def on_update(self, payload):
        payload['time'] = timezone.now().timestamp()
        self.stdout.write(f'[{timezone.now().isoformat()}] Writing', ending='\t')
        try:
            with open(self.options['output'], 'a') as f:
                f.write(json.dumps(payload, cls=DecimalEncoder) + '\n')
            self.stdout.write(self.style.SUCCESS('OK'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error writing update: {e}'))