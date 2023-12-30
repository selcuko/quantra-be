from datetime import datetime, timedelta
import threading
from django.apps import AppConfig
import pytz
from logger import logger
from models import interval_to_minutes


def continue_sessions():
    try:
        from quantapi.models import Session

        for session in Session.objects.filter(status=Session.Status.ONGOING):
            try:
                pass
            except:
                logger.error(f'Failed to resume session {session} on startup.', exc_info=True)
    except:
        logger.error('Failed to continue sessions on startup.', exc_info=True)


class QuantapiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'quantapi'
    verbose_name = 'Quant API'

    def ready(self) -> None:
        threading.Thread(target=continue_sessions, daemon=True).start()

            
