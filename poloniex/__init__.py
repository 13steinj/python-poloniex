"""Poloniex API wrapper"""

from calendar import timegm
from datetime import datetime
from hashlib import sha512
from functools import partial

import hmac
import time
import itertools
import logging

from requests import Session
from requests.exceptions import RequestException
from six import text_type, wraps
from six.moves.urllib.parse import urlencode

from poloniex.ratelimit import RateLimitEnforcer


logger = logging.getLogger(__name__)
defaultRetries = (0, 2, 5, 30)


class PoloniexError(Exception):
    """Exception for handling poloniex api errors """
    pass


class RetryException(PoloniexError):
    """Exception for retry decorator """
    pass


class PoloniexAPI(object):
    COMMANDS = []
    REQEUST_URL = None
    SESSION_CLASS = Session
    coach = RateLimitEnforcer()
    """The Poloniex Object!"""

    def __init__(self, timeout=None, retries=defaultRetries):
        self.logger = logger

        self.session = self.SESSION_CLASS()
        self.timeout, self.retries = timeout, retries

    @property
    def now_timestamp(self):
        return timegm(datetime.utcnow())

    def _retry(self, func):
        """Retry decorator"""
        @wraps(func)
        def retrying(*args, **kwargs):
            problems = []
            for delay in itertools.chain(self.retries, [None]):
                try:
                    # attempt call
                    return func(*args, **kwargs)
                except RequestException as problem:
                    problems.append(problem)
                    if delay is None:
                        logger.debug(problems)
                        raise RetryException(
                            'retries exhausted ' + text_type(problem))
                    else:
                        # log exception and wait
                        logger.debug(problem)
                        logger.info("-- delaying for %ds", delay)
                        time.sleep(delay)
        return retrying

    def __call__(self, command, **args):
        """ Main Api Function
        - encodes and sends <command> with optional [args] to Poloniex api
        - raises 'poloniex.PoloniexError' if an api key or secret is missing
            (and the command is 'private'), if the <command> is not valid, or
            if an error is returned from poloniex.com
        - returns decoded json api message """
        # get command type

        # pass the command
        args['command'] = command
        payload = {
            'timeout': self.timeout,
            'url': {
                type(self) is PoloniexPublicAPI:
                    PoloniexPublicAPI.REQEUST_URL,
                type(self) is PoloniexPrivateAPI:
                    PoloniexPrivateAPI.REQEUST_URL
            }[True]
        }

        return self._retry(self._make_request)(payload, args)

    def __getattr__(self, item):
        if item in self.COMMANDS:
            return partial(self, item)
        raise AttributeError(PoloniexError("Invalid Command!: %s" % item))

    def _handleResponse(self, resp):
        """ Handles returned data from poloniex"""
        try:
            out = resp.json()
        except ValueError:
            self.logger.error(resp.text)
            raise PoloniexError('Invalid json response returned')

        # check if poloniex returned an error
        if 'error' in out:
            if "Nonce must be greater" in out['error']:
                self._nonce = int(
                    out['error'].split('.')[0].split()[-1])
                raise RequestException('PoloniexError ' + out['error'])
            elif "please try again" in out['error'].lower():
                raise RequestException('PoloniexError ' + out['error'])
            else:
                raise PoloniexError(out['error'])
        return out


class PoloniexPublicAPI(PoloniexAPI):
    REQUEST_METHOD = "get"
    REQEUST_URL = "http://poloniex.com/public"
    COMMANDS = [
        'returnTicker',
        'return24hVolume',
        'returnOrderBook',
        'returnTradeHistory',
        'returnChartData',
        'returnCurrencies',
        'returnLoanOrders'
    ]

    def __init__(self, timeout=None, retries=defaultRetries, coach=None):
        super(PoloniexPublicAPI, self).__init__(timeout, retries)
        self.coach = coach
        if coach is None:
            self.coach = RateLimitEnforcer()

    def _make_request(self, payload, args):
        payload['params'] = args
        with self.coach:
            return self._handleResponse(
                getattr(self.session,
                        PoloniexPublicAPI.REQUEST_METHOD)(**payload))


class PoloniexPrivateAPI(PoloniexPublicAPI):
    REQEUST_METHOD = "post"
    REQEUST_URL = "http://poloniex.com/tradingApi"
    COMMANDS = [
        'returnBalances',
        'returnCompleteBalances',
        'returnDepositAddresses',
        'generateNewAddress',
        'returnDepositsWithdrawals',
        'returnOpenOrders',
        'returnTradeHistory',
        'returnAvailableAccountBalances',
        'returnTradableBalances',
        'returnOpenLoanOffers',
        'returnOrderTrades',
        'returnActiveLoans',
        'returnLendingHistory',
        'createLoanOffer',
        'cancelLoanOffer',
        'toggleAutoRenew',
        'buy',
        'sell',
        'cancelOrder',
        'moveOrder',
        'withdraw',
        'returnFeeInfo',
        'transferBalance',
        'returnMarginAccountSummary',
        'marginBuy',
        'marginSell',
        'getMarginPosition',
        'closeMarginPosition'
    ]

    def __init__(
            self, key, secret, timeout=None,
            retries=defaultRetries, coach=None,
            start_nonce=None, nonce_lock=None
    ):
        super(PoloniexPrivateAPI, self).__init__(timeout, retries, coach)
        self.key, self.secret = key, secret
        self._nonce, self.nonce_lock = start_nonce, nonce_lock
        if start_nonce is None:
            self._nonce = timegm(datetime.utcnow().timetuple())

    def __getattr__(self, item):
        if not self.key or not self.secret:
            raise AttributeError(PoloniexError("An Api Key and Secret needed!"))
        return super(PoloniexPrivateAPI, self).__getattr__(item)

    def _make_request(self, payload, args):
        payload['data'] = args
        with self.coach:
            with self.nonce_lock:  # private api needs an incrementing nonce
                self._nonce += 1
                args['nonce'] = self._nonce
                payload['headers'] = {
                    'Sign': hmac.new(
                        self.secret,
                        urlencode(args),
                        sha512
                    ).hexdigest(),
                    'Key': self.key
                }
                return self._handleResponse(
                    getattr(self.session,
                            PoloniexPrivateAPI.REQEUST_METHOD)(**payload))


class Poloniex(PoloniexPrivateAPI):
    COMMANDS = PoloniexPublicAPI.COMMANDS + PoloniexPrivateAPI.COMMANDS

    def __getattr__(self, item):
        if item in PoloniexPrivateAPI.COMMANDS:
            return super(Poloniex, self).__getattr__(item)
        return super(PoloniexPrivateAPI, self).__getattr__(item)

    def _make_request(self, payload, args):
        if args['command'] in PoloniexPrivateAPI.COMMANDS:
            return super(Poloniex, self)._make_request(payload, args)
        return super(PoloniexPrivateAPI, self)._make_request(payload, args)
