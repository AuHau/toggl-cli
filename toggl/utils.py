import datetime
import os

import dateutil.parser
import iso8601
import pytz
import requests
from six.moves import configparser as ConfigParser


# ----------------------------------------------------------------------------
# Singleton
# ----------------------------------------------------------------------------
class Singleton(type):
    """
    Defines a way to implement the singleton pattern in Python.
    From: http://stackoverflow.com/questions/31875/is-there-a-simple-elegant-way-to-define-singletons-in-python/33201#33201

    To use, simply put the following line in your class definition:
        __metaclass__ = Singleton
    """

    def __init__(cls, name, bases, dict):
        super(Singleton, cls).__init__(name, bases, dict)
        cls.instance = None

    def __call__(cls, *args, **kw):
        if cls.instance is None:
            cls.instance = super(Singleton, cls).__call__(*args, **kw)
        return cls.instance


# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
class Config(object):
    """
    Singleton. toggl configuration data, read from ~/.togglrc.
    Properties:
        auth - (username, password) tuple.
    """

    __metaclass__ = Singleton

    def __init__(self):
        """
        Reads configuration data from ~/.togglrc.
        """
        self.cfg = ConfigParser.RawConfigParser({'continue_creates': 'false'})
        if self.cfg.read(os.path.expanduser('~/.togglrc')) == []:
            self._create_empty_config()
            raise IOError("Missing ~/.togglrc. A default has been created for editing.")

    def _create_empty_config(self):
        """
        Creates a blank ~/.togglrc.
        """
        cfg = ConfigParser.RawConfigParser()
        cfg.add_section('auth')
        cfg.set('auth', 'username', 'user@example.com')
        cfg.set('auth', 'password', 'toggl_password')
        cfg.set('auth', 'api_token', 'your_api_token')
        cfg.add_section('options')
        cfg.set('options', 'timezone', 'UTC')
        cfg.set('options', 'time_format', '%I:%M%p')
        cfg.set('options', 'prefer_token', 'true')
        cfg.set('options', 'continue_creates', 'true')
        with open(os.path.expanduser('~/.togglrc'), 'w') as cfgfile:
            cfg.write(cfgfile)
        os.chmod(os.path.expanduser('~/.togglrc'), 0o600)

    def get(self, section, key):
        """
        Returns the value of the configuration variable identified by the
        given key within the given section of the configuration file. Raises
        ConfigParser exceptions if the section or key are invalid.
        """
        return self.cfg.get(section, key).strip()

    def get_auth(self):
        if self.get('options', 'prefer_token').lower() == 'true':
            return requests.auth.HTTPBasicAuth(self.get('auth', 'api_token'),
                                               'api_token')
        else:
            return requests.auth.HTTPBasicAuth(self.get('auth', 'username'),
                                               self.get('auth', 'password'))


# ----------------------------------------------------------------------------
# DateAndTime
# ----------------------------------------------------------------------------
class DateAndTime(object):
    """
    Singleton date and time functions. Mostly utility functions. All
    the timezone and datetime functionality is localized here.
    """

    __metaclass__ = Singleton

    def __init__(self):
        self.tz = pytz.timezone(Config().get('options', 'timezone'))

    def duration_since_epoch(self, dt):
        """
        Converts the given localized datetime object to the number of
        seconds since the epoch.
        """
        return (dt.astimezone(pytz.UTC) - datetime.datetime(1970, 1, 1, tzinfo=pytz.UTC)).total_seconds()

    def duration_str_to_seconds(self, duration_str):
        """
        Parses a string of the form [[Hours:]Minutes:]Seconds and returns
        the total time in seconds.
        """
        elements = duration_str.split(':')
        duration = 0
        if len(elements) == 3:
            duration += int(elements[0]) * 3600
            elements = elements[1:]
        if len(elements) == 2:
            duration += int(elements[0]) * 60
            elements = elements[1:]
        duration += int(elements[0])

        return duration

    def elapsed_time(self, seconds, suffixes=['y', 'w', 'd', 'h', 'm', 's'], add_s=False, separator=''):
        """
        Takes an amount of seconds and turns it into a human-readable amount
        of time.
        From http://snipplr.com/view.php?codeview&id=5713
        """
        # the formatted time string to be returned
        time = []

        # the pieces of time to iterate over (days, hours, minutes, etc)
        # - the first piece in each tuple is the suffix (d, h, w)
        # - the second piece is the length in seconds (a day is 60s * 60m * 24h)
        parts = [(suffixes[0], 60 * 60 * 24 * 7 * 52),
                 (suffixes[1], 60 * 60 * 24 * 7),
                 (suffixes[2], 60 * 60 * 24),
                 (suffixes[3], 60 * 60),
                 (suffixes[4], 60),
                 (suffixes[5], 1)]

        # for each time piece, grab the value and remaining seconds, and add it to
        # the time string
        for suffix, length in parts:
            value = seconds // length
            if value > 0:
                seconds = seconds % length
                time.append('{}{}'.format(str(value),
                                          (suffix, (suffix, suffix + 's')[value > 1])[add_s]))
            if seconds < 1:
                break

        return separator.join(time)

    def format_time(self, time):
        """
        Formats the given datetime object according to the strftime() options
        from the configuration file.
        """
        format = Config().get('options', 'time_format')
        return time.strftime(format)

    def last_minute_today(self):
        """
        Returns 23:59:59 today as a localized datetime object.
        """
        return datetime.datetime.now(self.tz) \
            .replace(hour=23, minute=59, second=59, microsecond=0)

    def now(self):
        """
        Returns "now" as a localized datetime object.
        """
        return self.tz.localize(datetime.datetime.now())

    def parse_local_datetime_str(self, datetime_str):
        """
        Parses a local datetime string (e.g., "2:00pm") and returns
        a localized datetime object.
        """
        return self.tz.localize(dateutil.parser.parse(datetime_str))

    def parse_iso_str(self, iso_str):
        """
        Parses an ISO 8601 datetime string and returns a localized datetime
        object.
        """
        return iso8601.parse_date(iso_str).astimezone(self.tz)

    def start_of_today(self):
        """
        Returns 00:00:00 today as a localized datetime object.
        """
        return self.tz.localize(
            datetime.datetime.combine(datetime.date.today(), datetime.time.min)
        )

    def start_of_yesterday(self):
        """
        Returns 00:00:00 yesterday as a localized datetime object.
        """
        return self.tz.localize(
            datetime.datetime.combine(datetime.date.today(), datetime.time.min) -
            datetime.timedelta(days=1)  # subtract one day from today at midnight
        )


# ----------------------------------------------------------------------------
# Logger
# ----------------------------------------------------------------------------
class Logger(object):
    """
    Custom logger class. Created because I got tired of seeing logging message
    from all the modules imported here. There's no easy way to limit logging
    to this file only.
    """

    # Logging levels.
    NONE = 0
    INFO = 1
    DEBUG = 2

    # Current level.
    level = NONE

    @staticmethod
    def debug(msg, end="\n"):
        """
        Prints msg if the current logging level >= DEBUG.
        """
        if Logger.level >= Logger.DEBUG:
            print("{}{}".format(msg, end)),

    @staticmethod
    def info(msg, end="\n"):
        """
        Prints msg if the current logging level >= INFO.
        """
        if Logger.level >= Logger.INFO:
            print("{}{}".format(msg, end)),


# ----------------------------------------------------------------------------
# toggl
# ----------------------------------------------------------------------------
def toggl(url, method, data=None, headers={'content-type': 'application/json'}):
    """
    Makes an HTTP request to toggl.com. Returns the raw text data received.
    """
    from .toggl import TOGGL_URL

    url = "{}{}".format(TOGGL_URL, url)
    try:
        if method == 'delete':
            r = requests.delete(url, auth=Config().get_auth(), data=data, headers=headers)
        elif method == 'get':
            r = requests.get(url, auth=Config().get_auth(), data=data, headers=headers)
        elif method == 'post':
            r = requests.post(url, auth=Config().get_auth(), data=data, headers=headers)
        elif method == 'put':
            r = requests.post(url, auth=Config().get_auth(), data=data, headers=headers)
        else:
            raise NotImplementedError('HTTP method "{}" not implemented.'.format(method))
        r.raise_for_status()  # raise exception on error
        return r.text
    except Exception as e:
        print('Sent: {}'.format(data))
        print(e)
        print(r.text)
        # sys.exit(1)
