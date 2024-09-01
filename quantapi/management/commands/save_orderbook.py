from decimal import Decimal
import json
import os
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from loops.liveloop import LiveLoop
from quantapi.models import Market, MarketSymbol
from queue import Queue
from threading import Thread


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
        parser.add_argument('--output', required=True, type=str, help='Output file path')
        parser.add_argument('--overwrite', action='store_true', help='Overwrite the file if it already exists')
        parser.add_argument('--futures', action='store_true', help='Use futures interface instead of spot', default=False)

    def handle(self, *args, **options):
        self.options = options
        self.futures = options['futures']
        try:
            self.market = Market.objects.get(exchange_name=self.options['market'].upper())
        except Market.DoesNotExist:
            raise CommandError(f'Market {self.options["market"]} not found.')
        try:
            symbol = self.options['symbol'].lower().replace('-', '').replace('usdt', '').upper()
            contract_type = MarketSymbol.ContractType.FUTURES if self.futures else MarketSymbol.ContractType.SPOT
            self.symbol = MarketSymbol.objects.get(contract_type=contract_type, market=self.market, base=symbol)
        except MarketSymbol.DoesNotExist:
            raise CommandError(f'Symbol {symbol} not found in {self.market.exchange_name}.')
        self.buffer = Queue()
        self.prep_file()
        self.interface = self.market.get_interface()
        self.prep_snapshot()
        worker_thread = Thread(target=self.worker)
        worker_thread.start()
        self.interface.init_orderbook_websocket(
            self.symbol,
            self.on_update,
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
            }
            f.write(json.dumps(header_payload) + '\n')

    def prep_snapshot(self):
        full_ob = self.interface.get_full_orderbook(self.symbol)
        full_ob['time'] = timezone.now().timestamp()
        full_ob['type'] = 'snapshot'
        with open(self.options['output'], 'a') as f:
            f.write(json.dumps(full_ob, cls=DecimalEncoder) + '\n')

    def on_update(self, payload):
        payload['time'] = timezone.now().timestamp()
        self.buffer.put(payload)

    def worker(self):
        while True:
            payload = self.buffer.get()
            self.stdout.write(f'[{timezone.now().isoformat()}] Writing (Queue: {self.buffer.qsize()})', ending='\t')
            try:
                with open(self.options['output'], 'a') as f:
                    f.write(json.dumps(payload, cls=DecimalEncoder) + '\n')
                self.stdout.write(self.style.SUCCESS('OK'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error writing update: {e}'))