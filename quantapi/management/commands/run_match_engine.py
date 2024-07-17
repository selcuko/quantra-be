from django.core.management.base import BaseCommand
from loops import LiveLoop
from quantapi.models import MarketAccount


class MockLiveLoop(LiveLoop):
    def __init__(self, *args, **kwargs):
        pass

    def should_stop(self):
        return False

class Command(BaseCommand):
    help = 'Test command'

    def handle(self, *args, **options):
        iface = MarketAccount.objects.get(market__exchange_name='MEXC').get_interface()
        # using MockLiveLoop here to provide the thread with a stop condition in real world use
        iface.init_match_engine('BTC-USDT', '1 min', print, MockLiveLoop())
