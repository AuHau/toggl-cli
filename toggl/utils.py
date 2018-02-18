import datetime
import json
import os
from collections import defaultdict

import time
import dateutil.parser
import iso8601
import pytz
import requests
from six.moves import configparser
from builtins import input


# ----------------------------------------------------------------------------
# Singleton
# ----------------------------------------------------------------------------
class Singleton(type):
    """
    Defines a way to implement the singleton pattern in Python.
    From:
    http://stackoverflow.com/questions/31875/is-there-a-simple-elegant-way-to-define-singletons-in-python/33201#33201

    To use, simply put the following line in your class definition:
        __metaclass__ = Singleton
    """

    def __init__(cls, name, bases, dictionary):
        super(Singleton, cls).__init__(name, bases, dictionary)
        cls.instance = None

    def __call__(cls, *args, **kw):
        if cls.instance is None:
            cls.instance = super(Singleton, cls).__call__(*args, **kw)
        return cls.instance


class ConfigBootstrap(object):
    """
    Create config based on the input from the User
    """

    def _get_value(self, message, values=None, default=None, allow_empty=False, show_values=True):
        default_msg = ""
        if default:
            default_msg = " [default:{}]".format(default)

        values_msg = ""
        if show_values and values:
            values_msg = " " + '/'.join(values)

        result = input("\n{}:{}{}\n".format(message, values_msg, default_msg))

        if (not result or result == "") and default:
            return default

        if not values:

            if allow_empty:
                return result

            while result == "":
                result = input("The value must not be empty!\n")

            return result

        while result not in values:
            result = input("Unrecognized value, please use one of following: {}{}\n".format(
                '/'.join(values), default_msg
            ))

        return result

    def _are_credentials_valid(self, *, api_token=None, username=None, password=None):
        from .toggl import TOGGL_URL

        if api_token:
            auth = requests.auth.HTTPBasicAuth(api_token, 'api_token')

        elif username and password:
            auth = requests.auth.HTTPBasicAuth(username, password)
        else:
            raise Exception("There has to be specified at least one way of authentication! API token or credentials!")

        url = "{}{}".format(TOGGL_URL, "/me")
        r = requests.get(url, auth=auth, headers={'content-type': 'application/json'})

        if r.status_code == 200:
            return True
        else:
            return False

    def start(self, validate_credentials=True):
        print(""" _____                 _   _____  _     _____ 
|_   _|               | | /  __ \| |   |_   _|
  | | ___   __ _  __ _| | | /  \/| |     | |  
  | |/ _ \ / _` |/ _` | | | |    | |     | |  
  | | (_) | (_| | (_| | | | \__/\| |_____| |_ 
  \_/\___/ \__, |\__, |_|  \____/\_____/\___/ 
            __/ | __/ |                       
           |___/ |___/                        

Welcome to Toggl CLI!\nWe need to setup some configuration before you start using this awesome tool!\n""")

        values = defaultdict(dict)
        type_auth = self._get_value("Type of authentication you want to use", ["apitoken", "credentials"], "apitoken")

        if type_auth == "apitoken":
            api_token = self._get_value("API token")

            if validate_credentials:
                while not self._are_credentials_valid(api_token=api_token):
                    print("The API token is not valid! We could not sign-up to Toggl with it...")
                    api_token = self._get_value("API token")

            values["auth"]["api_token"] = api_token
        else:
            print("Be aware! Your username and password will be stored in plain text in the ~/.togglerc file!")
            username = self._get_value("Username")
            password = self._get_value("Password")

            if validate_credentials:
                while not self._are_credentials_valid(username=username, password=password):
                    print("The API token is not valid! We could not sign-up to Toggl with it...")
                    username = self._get_value("Username")
                    password = self._get_value("Password")

            values["auth"]["username"] = username
            values["auth"]["password"] = password

        local_timezone = time.tzname[0]
        values["options"]["timezone"] = self._get_value("Used timezone", pytz.all_timezones, local_timezone, show_values=False)
        values["options"]["continue_creates"] = self._get_value("Continue command will create new entry",
                                                                ["true", "false"], "true")

        return values


# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
class Config(configparser.RawConfigParser):
    """
    Singleton. toggl configuration data, read from ~/.togglrc.
    Properties:
        auth - (username, password) tuple.
    """

    __metaclass__ = Singleton

    DEFAULT_VALUES = {
        'continue_creates': 'true',
        'time_format': '%I:%M%p',
        'day_first': 'false',
        'year_first': 'false',
    }

    CONFIG_PATH = os.path.expanduser('~/.togglrc')

    ENV_NAME_API_TOKEN = 'TOGGL_API_TOKEN'
    ENV_NAME_USERNAME = 'TOGGL_USERNAME'
    ENV_NAME_PASSWORD = 'TOGGL_PASSWORD'

    def __init__(self):
        """
        Reads configuration data from ~/.togglrc.
        """
        super().__init__(self.DEFAULT_VALUES)

        if not self.read(self.CONFIG_PATH):
            self._init_new_config()

    def _init_new_config(self):
        values_dict = ConfigBootstrap().start()
        self.read_dict(values_dict)

        with open(self.CONFIG_PATH, 'w') as cfgfile:
            self.write(cfgfile)
        os.chmod(self.CONFIG_PATH, 0o600)

    def get_auth(self):
        """
        Returns HTTPBasicAuth object to be used with request.

        Supports overriding of the configuration using environment variables:
        TOGGL_API_TOKEN, TOGGL_USERNAME and TOGGL_PASSWORD.

        :raises configparser.Error: When no credentials are available.
        :return: requests.auth.HTTPBasicAuth
        """
        env_api_token = os.getenv(self.ENV_NAME_API_TOKEN)
        env_username = os.getenv(self.ENV_NAME_USERNAME)
        env_password = os.getenv(self.ENV_NAME_PASSWORD)

        if env_api_token:
            return requests.auth.HTTPBasicAuth(env_api_token, 'api_token')

        if env_username and env_password:
            return requests.auth.HTTPBasicAuth(env_username, env_password)

        use_token = self.get("options", "prefer_token", fallback=None)

        if use_token is None:
            api_token = self.get('auth', 'api_token', fallback=None)

            if api_token is not None:
                return requests.auth.HTTPBasicAuth(api_token, 'api_token')

            username = env_username or self.get('auth', 'username', fallback=None)
            password = env_password or self.get('auth', 'password', fallback=None)

            if username is None and password is None:
                raise configparser.Error("There is no authentication configuration!")

            return requests.auth.HTTPBasicAuth(username, password)

        # Fallback to old style configuration with 'prefer_token'
        if use_token.lower() == 'true':
            return requests.auth.HTTPBasicAuth(self.get('auth', 'api_token'), 'api_token')
        else:
            return requests.auth.HTTPBasicAuth(self.get('auth', 'username'), self.get('auth', 'password'))


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

    def elapsed_time(self, seconds, suffixes=None, add_s=False, separator=''):
        """
        Takes an amount of seconds and turns it into a human-readable amount
        of time.
        From http://snipplr.com/view.php?codeview&id=5713
        """
        if suffixes is None:
            suffixes = ['y', 'w', 'd', 'h', 'm', 's']

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
        time_format = Config().get('options', 'time_format')
        return time.strftime(time_format)

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

    def parse_local_datetime_str(self, datetime_str, day_first=False, year_first=False):
        """
        Parses a local datetime string (e.g., "2:00pm") and returns
        a localized datetime object.
        """
        return self.tz.localize(dateutil.parser.parse(datetime_str, dayfirst=day_first, yearfirst=year_first))

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
def toggl(url, method, data=None, headers=None):
    """
    Makes an HTTP request to toggl.com. Returns the parsed JSON as dict.
    """
    from .toggl import TOGGL_URL

    if headers is None:
        headers = {'content-type': 'application/json'}

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
        return json.loads(r.text)
    except Exception as e:
        print('Sent: {}'.format(data))
        print(e)
        # sys.exit(1)
