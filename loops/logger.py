from logger import logger
'''
Collection of logging functions specific to the loops module.
'''
def log_ghost_session():
    logger.error('No meaningful equity left in the Session or SessionGroup (i.e. ghost state)')
def unexpectedly_exiting():
    logger.error('Unexpectedly exiting loop.')
