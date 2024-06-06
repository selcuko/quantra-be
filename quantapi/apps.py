from datetime import datetime, timedelta
import threading
from django.apps import AppConfig
import pytz
from logger import logger
from models import interval_to_minutes
from ob_server import start_orderbook_server


def continue_sessions():
    PURGE_THRESHOLD = 100
    from quantapi.models import Session
    sessions = list(Session.objects.filter(status=Session.Status.ONGOING))
    for session in sessions:
        try:
            if session.last_kline_timestamp:
                session_suspended_for = datetime.now(pytz.utc) - session.last_kline_timestamp
                # resume session if it was suspended for less than 100 candles
                if session_suspended_for < timedelta(minutes=interval_to_minutes(session.freq) * PURGE_THRESHOLD):
                    session.resume()
                else:
                    session.status = Session.Status.PURGED
                    session.details = f'Session was suspended for too long ({PURGE_THRESHOLD} candles), continue manually if needed.'
                    session.save()
                    logger.critical(f'Session {session} was suspended for too long ({PURGE_THRESHOLD} candles), purged.', exc_info=True, extra={'n_type': 'LOG', 'subject': 'Purged session on reboot', 'details': session.details})
            else:
                session.resume()
        except Exception as e:
            session.status = Session.Status.ERROR
            session.ended = datetime.now(pytz.utc)
            session.details = repr(e)
            session.save()
            logger.critical(f'Failed to resume session {session} on startup.', exc_info=True, extra={'n_type': 'CRASH', 'subject': 'Failed to resume session on reboot', 'details': session.details})

    from watchdog import watchdog_loop
    threading.Thread(target=watchdog_loop, daemon=True).start()


def symbol_metrics_update_loop():
    from quantapi.management.commands.update_symbol_metrics import Command
    while True:
        try:
            threading.Event().wait(60 * 60)
            Command().handle()
            threading.Event().wait(60 * 60 * 4)
        except:
            logger.warning('Failed to update symbol metrics.', exc_info=True)


class QuantapiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'quantapi'
    verbose_name = 'Quant API'

    def ready(self) -> None:
        # check if this is a migration or not
        import sys
        if 'runserver' in sys.argv or 'quant.wsgi' in sys.argv:
            threading.Thread(target=continue_sessions, daemon=True).start()
            threading.Thread(target=symbol_metrics_update_loop, daemon=True).start()
            threading.Thread(target=start_orderbook_server).start()

