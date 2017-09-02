from poloniex import custom_threading as threading


class RateLimitEnforcer(object):
    """Ratelimits the API wrapper to callLimit calls per timeFrame"""

    def __init__(self, timeFrame=1.0, callLimit=6):
        """
        timeFrame = float time in secs [default = 1.0]
        callLimit = int max amount of calls per 'timeFrame' [default = 6]
        """
        self.semaphore = threading.Semaphore(callLimit)
        self.timer = threading.RecurrentTimer(timeFrame, self.semaphore.clear)
        self.timer.setDaemon(True)

    def wait(self):
        """ Makes sure our api calls don't go past the api call limit """
        if self.timer.ident is not None:  # start the timer once
            self.timer.start()
        self.semaphore.acquire()

    __enter__ = wait

    def __exit__(self, t, v, tb):
        pass
