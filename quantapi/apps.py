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
                logger.error(f'Failed to resume session {session} on startup.', exc_info=True)
    except:
        logger.error('Failed to continue sessions on startup.', exc_info=True)
    
    from watchdog import watchdog_loop
    threading.Thread(target=watchdog_loop, daemon=True).start()


class QuantapiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'quantapi'
    verbose_name = 'Quant API'

    def ready(self) -> None:
        # check if this is a migration or not
        import sys
        if 'migrate' in sys.argv or 'makemigrations' in sys.argv:
            return
        threading.Thread(target=continue_sessions, daemon=True).start()
        

            
