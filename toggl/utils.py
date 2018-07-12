import datetime
import json
import os
from abc import ABCMeta
from collections import defaultdict

import time

import click
import dateutil.parser
import inquirer
import iso8601
import pytz
import requests
from six.moves import configparser
from builtins import input
from six import with_metaclass
from tzlocal import get_localzone


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


class CachedFactoryMeta(type):
    """
    Similar to Singleton patter, except there are more instances cached based on a input parameter.
    It utilizes Factory pattern and forbids direct instantion of the class.
    """

    SENTINEL_KEY = '20800fa4-c75d-4c2c-9c99-fb35122e1a18'

    def __new__(mcs, name, bases, namespace):
        mcs.cache = {}

        def new__init__(self):
            raise ValueError('Cannot directly instantiate new object, you have to use \'factory\' method for that!')

        old_init = namespace.get('__init__')
        namespace['__init__'] = new__init__

        def factory(cls_obj, key=sentinel, *args, **kwargs):
            # Key with None are not cached
            if key is None:
                obj = cls_obj.__new__(cls_obj, key, *args, **kwargs)
                old_init(obj, key, *args, **kwargs)
                return obj

            cached_key = mcs.SENTINEL_KEY if key == sentinel else key

            if cached_key in mcs.cache:
                return mcs.cache[cached_key]

            if key == sentinel:
                obj = cls_obj.__new__(cls_obj, *args, **kwargs)
                old_init(obj, *args, **kwargs)
            else:
                obj = cls_obj.__new__(cls_obj, key, *args, **kwargs)
                old_init(obj, key, *args, **kwargs)

            mcs.cache[cached_key] = obj

            return obj

        namespace['factory'] = classmethod(factory)
        return super().__new__(mcs, name, bases, namespace)


class ABCCachedFactoryMeta(CachedFactoryMeta, ABCMeta):
    pass


class ConfigBootstrap(object):
    """
    Create config based on the input from the User
    """

    def __init__(self):
        self.workspaces = None

    def _are_credentials_valid(self, answers, credential):
        config = self._build_tmp_config(answers, credential)

        try:
            toggl("/me", "get", config=config)
            return True
        except Exception as e:
            Logger.debug(e)
            return False

    def _build_tmp_config(self, answers, credential=None):
        config = Config.factory(None)
        config.add_section("auth")

        if answers['type_auth'] == "API token":
            config.set('auth', 'api_token', credential or answers['API token'])
        else:
            config.set('auth', 'username', answers['username'])
            config.set('auth', 'password', credential or answers['password'])

        return config

    def _get_workspaces(self, answers):
        from toggl.api import WorkspaceList
        config = self._build_tmp_config(answers)

        if self.workspaces is None:
            self.workspaces = []
            for workspace in WorkspaceList(config):
                self.workspaces.append(workspace['name'])

        return self.workspaces

    def _map_answers(self, answers):
        from toggl.api import WorkspaceList

        config = self._build_tmp_config(answers)
        default_workspace_id = WorkspaceList(config).find_by_name(answers['default workspace'])['id']

        if answers['type_auth'] == "API token":
            auth = {
                'api_token': answers['API token']
            }
        else:
            auth = {
                'username': answers['username'],
                'password': answers['password']
            }

        return {
            'auth': auth,
            'options': {
                'default_workspace': default_workspace_id,
                'timezone': answers['timezone'],
                'continue_creates': answers['continue_creates'],
            }
        }

    def start(self, validate_credentials=True):
        click.secho(""" _____                 _   _____  _     _____ 
|_   _|               | | /  __ \| |   |_   _|
  | | ___   __ _  __ _| | | /  \/| |     | |  
  | |/ _ \ / _` |/ _` | | | |    | |     | |  
  | | (_) | (_| | (_| | | | \__/\| |_____| |_ 
  \_/\___/ \__, |\__, |_|  \____/\_____/\___/ 
            __/ | __/ |                       
           |___/ |___/                        
""", fg="red")
        click.echo("Welcome to Toggl CLI!\n"
                   "We need to setup some configuration before you start using this awesome tool!\n")

        click.echo("{} Your credentials will be stored in plain-text inside of the configuration!\n".format(
            click.style("Warning!", fg="yellow", bold=True)
        ))

        local_timezone = str(get_localzone())
        questions = [
            inquirer.List('type_auth', message="Type of authentication you want to use",
                          choices=["API token", "Credentials"]),

            inquirer.Password('API token', message="Your API token", ignore=lambda x: x['type_auth'] != 'API token',
                              validate=lambda answers, current: not validate_credentials
                                                                or self._are_credentials_valid(answers, current)),

            inquirer.Text('username', message="Your Username", ignore=lambda x: x['type_auth'] != 'Credentials'),

            inquirer.Password('password', message="Your Password", ignore=lambda x: x['type_auth'] != 'Credentials',
                              validate=lambda answers, current: not validate_credentials
                                        or self._are_credentials_valid(answers)),

            inquirer.List('default workspace', message="Default workspace which will be used when no workspace is provided",
                          choices=lambda answers: self._get_workspaces(answers)),

            inquirer.Text('timezone', 'Used timezone', default=local_timezone, show_default=True,
                          validate=lambda answers, current: current in pytz.all_timezones_set),

            inquirer.Confirm('continue_creates', message="Continue command will create new entry", default=True)
        ]

        answers = inquirer.prompt(questions)

        if answers is None:
            click.secho("We were not able to setup the needed configuration and we are unfortunately not able to "
                        "proceed without it", bg="white", fg="red")
            exit(-1)

        click.echo("\nConfiguration successfully finished!\nNow continuing with your command:\n\n")

        return self._map_answers(answers)


# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
sentinel = object()


class Config(with_metaclass(ABCCachedFactoryMeta, configparser.RawConfigParser)):
    """
    Singleton. toggl configuration data, read from ~/.togglrc.
    Properties:
        auth - (username, password) tuple.
    """

    DEFAULT_VALUES = {
        'continue_creates': 'True',
        'time_format': '%I:%M%p',
        'day_first': 'False',
        'year_first': 'False',
    }

    DEFAULT_CONFIG_PATH = os.path.expanduser('~/.togglrc')

    ENV_NAME_API_TOKEN = 'TOGGL_API_TOKEN'
    ENV_NAME_USERNAME = 'TOGGL_USERNAME'
    ENV_NAME_PASSWORD = 'TOGGL_PASSWORD'

    def __init__(self, config_path=sentinel):
        """
        Reads configuration data from ~/.togglrc.
        """
        super().__init__(self.DEFAULT_VALUES)

        self.config_path = self.DEFAULT_CONFIG_PATH if config_path == sentinel else config_path

        # There are use-cases when we do not want to load config from config file
        # and just build the config during runtime
        if self.config_path is not None and not self.read(self.config_path):
            self._init_new_config()

    def _init_new_config(self):
        values_dict = ConfigBootstrap().start()
        self.read_dict(values_dict)

        with open(self.config_path, 'w') as cfgfile:
            self.write(cfgfile)
        os.chmod(self.config_path, 0o600)

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
def toggl(url, method, data=None, headers=None, config=None):
    """
    Makes an HTTP request to toggl.com. Returns the parsed JSON as dict.
    """
    from .toggl import TOGGL_URL

    if headers is None:
        headers = {'content-type': 'application/json'}

    if config is None:
        config = Config.factory()

    url = "{}{}".format(TOGGL_URL, url)
    if method == 'delete':
        r = requests.delete(url, auth=config.get_auth(), data=data, headers=headers)
    elif method == 'get':
        r = requests.get(url, auth=config.get_auth(), data=data, headers=headers)
    elif method == 'post':
        r = requests.post(url, auth=config.get_auth(), data=data, headers=headers)
    elif method == 'put':
        r = requests.post(url, auth=config.get_auth(), data=data, headers=headers)
    else:
        raise NotImplementedError('HTTP method "{}" not implemented.'.format(method))

    # TODO: Better error handling
    r.raise_for_status()  # raise exception on error
    return json.loads(r.text)

