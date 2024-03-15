from datetime import datetime, timedelta
import threading
from django.apps import AppConfig
import pytz
from logger import logger
from models import interval_to_minutes


def continue_sessions():
    try:
        from quantapi.models import Session
        sessions = list(Session.objects.filter(status=Session.Status.ONGOING))
        for session in sessions:
            try:
                if session.last_kline_timestamp:
                    session_suspended_for = datetime.now(pytz.utc) - session.last_kline_timestamp
                    # resume session if it was suspended for less than 100 candles
                    if session_suspended_for < timedelta(minutes=interval_to_minutes(session.freq) * 100):
                        session.resume()
                    else:
                        session.status = Session.Status.PURGED
                        session.save()
                else:
                    session.resume()
            except:
                session.status = Session.Status.ERROR
                session.save()
                logger.error(f'Failed to resume session {session} on startup.', exc_info=True)
    except:
        logger.error('Failed to continue sessions on startup.', exc_info=True)
    
    from watchdog import watchdog_loop
    threading.Thread(target=watchdog_loop, daemon=True).start()


def symbol_metrics_update_loop():
    from quantapi.management.commands.update_symbol_metrics import Command
    while True:
        try:
            Command().handle()
            threading.Event().wait(60 * 60 * 4)
        except:
            logger.error('Failed to update symbol metrics.', exc_info=True)


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
        

            
