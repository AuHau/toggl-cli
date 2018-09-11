import datetime
import json
import logging
import os
from collections import namedtuple
from pprint import pformat

import configparser
from traceback import format_stack

import click
import dateutil.parser
import inquirer
import iso8601
import pytz
import requests
from tzlocal import get_localzone

from . import exceptions

logger = logging.getLogger('toggl.utils')


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


class ClassAttributeModificationWarning(type):
    def __setattr__(cls, attr, value):
        logger.warning('You are modifying class attribute of \'{}\' class. You better know what you are doing!'
                       .format(cls.__name__))

        logger.debug(pformat(format_stack()))

        super(ClassAttributeModificationWarning, cls).__setattr__(attr, value)


class CachedFactoryWithWarningsMeta(CachedFactoryMeta, ClassAttributeModificationWarning):
    pass


class ConfigBootstrap:
    """
    Create config based on the input from the User
    """

    KEEP_TOGGLS_DEFAULT_WORKSPACE = '-- Keep Toggl\'s default --'

    def __init__(self):
        self.workspaces = None

    def _are_credentials_valid(self, answers, credential):
        config = self._build_tmp_config(answers, credential)

        try:
            toggl("/me", "get", config=config)
            return True
        except exceptions.TogglAuthenticationException as e:
            Logger.debug(e)
            return False

    def _build_tmp_config(self, answers, credential=None):
        config = Config.factory(None)

        if answers['type_auth'] == "API token":
            config.api_token = credential or answers['API token']
        else:
            config.username = answers['username']
            config.password = credential or answers['password']

        return config

    def _get_workspaces(self, answers):
        from toggl.api import Workspace
        config = self._build_tmp_config(answers)

        if self.workspaces is None:
            self.workspaces = [self.KEEP_TOGGLS_DEFAULT_WORKSPACE]
            for workspace in Workspace.objects.all(config=config):
                self.workspaces.append(workspace.name)

        return self.workspaces

    def _map_answers(self, answers):
        output = {
            'file_logging': answers['file_logging'],

            'timezone': answers['timezone'],
            'continue_creates': answers['continue_creates'],
        }

        if output['file_logging']:
            output['file_logging_path'] = os.path.expanduser(answers.get('file_logging_path'))

        if answers['default workspace'] != self.KEEP_TOGGLS_DEFAULT_WORKSPACE:
            from toggl.api import Workspace
            config = self._build_tmp_config(answers)
            output['default_wid'] = Workspace.objects.get(name=answers['default workspace'], config=config).id

        if answers['type_auth'] == "API token":
            output['api_token'] = answers['API token']
        else:
            output['username'] = answers['username']
            output['password'] = answers['password']

        return output

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

            inquirer.List('default workspace', message="Should TogglCli use different default workspace from Toggl's "
                                                       "setting?",
                          choices=lambda answers: self._get_workspaces(answers)),

            inquirer.Text('timezone', 'Used timezone', default=local_timezone, show_default=True,
                          validate=lambda answers, current: current in pytz.all_timezones_set),

            inquirer.Confirm('continue_creates', message="Continue command will create new entry", default=True),
            inquirer.Confirm('file_logging', message="Enable logging of togglCli actions into file?", default=False),
            inquirer.Path('file_logging_path', message="Path to the log file", ignore=lambda x: not x['file_logging'],
                          default='~/.toggl_log'),
        ]

        answers = inquirer.prompt(questions)

        if answers is None:
            click.secho("We were not able to setup the needed configuration and we are unfortunately not able to "
                        "proceed without it.", bg="white", fg="red")
            exit(-1)

        click.echo("\nConfiguration successfully finished!\nNow continuing with your command:\n\n")

        return self._map_answers(answers)


# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
sentinel = object()

IniEntry = namedtuple('IniEntry', ['section', 'type'])


class IniConfigMixin:
    INI_MAPPING = {}
    DEFAULT_CONFIG_PATH = os.path.expanduser('~/.togglrc')

    def __init__(self, config_path=sentinel, **kwargs):
        self._config_path = self.DEFAULT_CONFIG_PATH if config_path == sentinel else config_path
        self._store = configparser.ConfigParser()
        self._loaded = False

        if self._config_path is not None:
            self._loaded = self._store.read(self._config_path)

        super().__init__(**kwargs)

    def _resolve_type(self, entry, item):
        if entry.type == bool:
            return self._store.getboolean(entry.section, item, fallback=None)
        elif entry.type == int:
            return self._store.getint(entry.section, item, fallback=None)
        elif entry.type == float:
            return self._store.getfloat(entry.section, item, fallback=None)
        else:
            return self._store.get(entry.section, item, fallback=None)

    def __getattribute__(self, item):
        mapping_dict = object.__getattribute__(self, 'INI_MAPPING')
        if item in mapping_dict:
            value = self._resolve_type(mapping_dict[item], item)
            if value is not None:
                return value

        return super(IniConfigMixin, self).__getattribute__(item)

    @property
    def is_loaded(self):
        return bool(self._loaded)

    def persist(self, items=None):
        if self._config_path is None:
            return

        for item in items:
            if item in self.INI_MAPPING:
                value = getattr(self, item)
                section = self.INI_MAPPING[item].section

                if not self._store.has_section(section):
                    self._store.add_section(section)

                self._store.set(section, item, value)

        with open(self._config_path, 'w') as config_file:
            self._store.write(config_file)


EnvEntry = namedtuple('EnvEntry', ['variable', 'type'])


class EnvConfigMixin:
    ENV_MAPPING = {}

    def __init__(self, read_env=True, **kwargs):
        self._read_env = read_env
        super(EnvConfigMixin, self).__init__(**kwargs)

    def _resolve_variable(self, entry):
        value = os.environ.get(entry.variable)

        if value is None:
            return None

        return entry.type(value)

    def __getattribute__(self, item):
        mapping_dict = object.__getattribute__(self, 'ENV_MAPPING')
        if item in mapping_dict:
            value = self._resolve_variable(mapping_dict[item])
            if value is not None:
                return value

        return super().__getattribute__(item)


# TODO: Migration of old version INI config
class Config(EnvConfigMixin, IniConfigMixin, metaclass=CachedFactoryWithWarningsMeta):
    """
    Configuration class which implements hierarchy lookup to enable overloading configurations
    based on several aspects.

    Supported hierarchy in order of priority:
         1) config instance's dict if present
         2) if associated env variable is present, then the env variable is used
         3) if config file specified, appropriate value is used
         4) class's dict for default fallback
    """

    # Default values
    continue_creates = True
    time_format = '%I:%M%p'
    day_first = False
    year_first = False
    file_logging = False
    file_logging_path = None

    ENV_MAPPING = {
        'api_token': EnvEntry('TOGGL_API_TOKEN', str),
        'user_name': EnvEntry('TOGGL_USERNAME', str),
        'password': EnvEntry('TOGGL_PASSWORD', str),
    }

    INI_MAPPING = {
        'api_token': IniEntry('auth', str),
        'user_name': IniEntry('auth', str),
        'password': IniEntry('auth', str),

        'file_logging': IniEntry('logging', bool),
        'file_logging_path': IniEntry('logging', str),

        'timezone': IniEntry('options', str),
        'continue_creates': IniEntry('options', bool),
        'year_first': IniEntry('options', bool),
        'day_first': IniEntry('options', bool),
        'default_wid': IniEntry('options', int),
    }

    def __init__(self, config_path=sentinel, read_env=True, **kwargs):
        super().__init__(config_path=config_path, read_env=read_env, **kwargs)

        self._user = None
        self._default_workspace = None

        for key, value in kwargs.items():
            if key.isupper() or key[0] == '_':
                raise AttributeError('You can not overload constants (eq. uppercase attributes) and private attributes'
                                     '(eq. variables starting with \'_\')!')

            setattr(self, key, value)

    def __getattribute__(self, item):
        """
        Implements hierarchy lookup as described in the class docstring.

        :param item:
        :return:
        """
        value_exists = True
        retrieved_value = None
        try:
            retrieved_value = object.__getattribute__(self, item)
        except AttributeError:
            value_exists = False

        # We are not interested in special attributes (private attributes or constants, methods)
        if item.isupper() or item[0] == '_' or (value_exists and callable(retrieved_value)):
            return retrieved_value

        # Retrieved value differs from the class attribute ==> it is instance's value, which has highest priority
        if value_exists and self._get_class_attribute(item) != retrieved_value:
            return retrieved_value

        return super().__getattribute__(item)

    def _get_class_attribute(self, attr):
        return self.__class__.__dict__.get(attr)

    def cli_bootstrap(self):
        values_dict = ConfigBootstrap().start()
        for key, value in values_dict.items():
            setattr(self, key, value)

    @property
    def user(self):
        # Cache the User defined by the instance's config
        if self._user is None:
            from .api import User
            self._user = User.objects.current_user(config=self)

        return self._user

    @property
    def default_workspace(self):
        if self._default_workspace is not None:
            return self._default_workspace

        try:
            from .api import Workspace
            self._default_workspace = Workspace.objects.get(self.default_wid, config=self)
            return self._default_workspace
        except AttributeError:
            pass

        return self.user.default_workspace

    def persist(self, items=None):
        # TODO: Decide if default values should be also persisted for backwards compatibility
        if items is None:
            items = []
            for item, value in vars(self).items():
                if item.isupper() or item[0] == '_' or self._get_class_attribute(item) == value:
                    continue

                items.append(item)

        super().persist(items)

    def get_auth(self):
        """
        Returns HTTPBasicAuth object to be used with request.

        :raises configparser.Error: When no credentials are available.
        :return: requests.auth.HTTPBasicAuth
        """
        try:
            return requests.auth.HTTPBasicAuth(self.api_token, 'api_token')
        except AttributeError:
            pass

        try:
            return requests.auth.HTTPBasicAuth(self.username, self.password)
        except AttributeError:
            raise configparser.Error("There is no authentication configuration!")


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
def handle_error(response):
    if response.status_code == 402:
        raise exceptions.TogglPremiumException(
            response.status_code, response.text,
            "Request tried to utilized Premium functionality on workspace which is not Premium!"
        )

    if response.status_code == 403:
        raise exceptions.TogglAuthenticationException(
            response.status_code, response.text,
            "Authentication credentials are not correct."
        )

    if response.status_code == 429:
        raise exceptions.TogglThrottlingException(
            response.status_code, response.text,
            "Toggl's API refused your request for throttling reasons."
        )

    if response.status_code == 404:
        raise exceptions.TogglNotFoundException(
            response.status_code, response.text,
            "Requested resource not found."
        )

    if 500 <= response.status_code < 600:
        raise exceptions.TogglServerException()

    raise exceptions.TogglApiException(
        response.status_code, response.text,
        "Toggl's API server returned {} code with message: {}"
        .format(response.status_code, response.text)
    )


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
    logger.info('Sending {} to \'{}\' data: {}'.format(method.upper(), url, json.dumps(data)))
    if method == 'delete':
        response = requests.delete(url, auth=config.get_auth(), data=data, headers=headers)
    elif method == 'get':
        response = requests.get(url, auth=config.get_auth(), data=data, headers=headers)
    elif method == 'post':
        response = requests.post(url, auth=config.get_auth(), data=data, headers=headers)
    elif method == 'put':
        response = requests.put(url, auth=config.get_auth(), data=data, headers=headers)
    else:
        raise NotImplementedError('HTTP method "{}" not implemented.'.format(method))

    if response.status_code >= 300:
        handle_error(response)

        response.raise_for_status()

    response_json = response.json()
    logger.debug('Response data:\n' + pformat(response_json))
    return response_json
