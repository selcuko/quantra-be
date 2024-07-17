from django.core.management.base import BaseCommand, CommandError
from quantapi.models import Session
from loops.liveloop_v2 import LiveLoop

class Command(BaseCommand):
    help = 'Run LiveLoop for a given session.'

    def add_arguments(self, parser):
        parser.add_argument('--session-id', type=int)

    def handle(self, *args, **options):
        try:
            session = Session.objects.get(id=options['session_id'])
        except Session.DoesNotExist:
            raise CommandError(f'Session with ID={options["session_id"]} does not exist.')
        loop = LiveLoop(session)
        loop.run()
        self.stdout.write(self.style.SUCCESS(f'Successfully started LiveLoop for Session ID={options["session_id"]}'))
