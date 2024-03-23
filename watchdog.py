import time
from quantapi.models import Session
from threading import enumerate


def handle_crashed_thread(thread_id):
    session = Session.objects.get(thread_id=thread_id)
    session.status = Session.Status.ERROR
    session.report = 'Thread crashed'
    session.save()
    # TODO: send notification


def watchdog(retry=0):
    return
    sessions = Session.objects.filter(status=Session.Status.ONGOING, thread_id__isnull=False)
    session_thread_ids = [session.thread_id for session in sessions]
    # compare session_thread_ids with current thread ids and ensure their name starts with LL
    current_thread_ids = [thread.ident for thread in enumerate() if thread.name.startswith('LL')]
    crashed_thread_ids = set(session_thread_ids) - set(current_thread_ids)
    if crashed_thread_ids:
        # recheck them to ensure they are not just sleeping
        if retry < 3:
            time.sleep(60)
            return watchdog(retry + 1)
        print('Crashed threads: ', crashed_thread_ids)
    for crashed_thread_id in crashed_thread_ids:
        handle_crashed_thread(crashed_thread_id)
    return {
        'all': session_thread_ids,
        'current': current_thread_ids,
        'crashed': crashed_thread_ids
    }


def watchdog_loop():
    while True:
        watchdog()
        time.sleep(60)


if __name__ == '__main__':
    watchdog()
