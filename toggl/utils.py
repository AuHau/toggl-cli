import configparser
import json
import logging
import os
from collections import namedtuple
from pprint import pformat
from traceback import format_stack
from typing import Union

import click
import inquirer
import pendulum
import requests

from . import exceptions

logger = logging.getLogger('toggl.utils')


# ----------------------------------------------------------------------------
# Meta utils
# ----------------------------------------------------------------------------
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
    SYSTEM_TIMEZONE = '-- Use system\'s timezone --'
    API_TOKEN_OPTION = 'API token'
    CREDENTIALS_OPTION = 'Credentials'

    def __init__(self):
        self.workspaces = None

    def _are_credentials_valid(self, **kwargs):
        config = self._build_tmp_config(**kwargs)

        try:
            toggl("/me", "get", config=config)
            return True
        except exceptions.TogglAuthenticationException as e:
            logger.debug(e)
            return False

    def _build_tmp_config(self, api_token=None, username=None, password=None):
        config = Config.factory(None)

        if api_token is not None:
            config.api_token = api_token
        else:
            config.username = username
            config.password = password

        return config

    def _get_workspaces(self, api_token):
        from toggl.api import Workspace
        config = self._build_tmp_config(api_token=api_token)

        if self.workspaces is None:
            self.workspaces = [self.KEEP_TOGGLS_DEFAULT_WORKSPACE]
            for workspace in Workspace.objects.all(config=config):
                self.workspaces.append(workspace.name)

        return self.workspaces

    def _map_answers(self, **answers):
        output = {
            'api_token': answers['api_token'],

            'file_logging': answers['file_logging'],
        }

        if answers['timezone'] == self.SYSTEM_TIMEZONE:
            output['timezone'] = 'local'

        if output['file_logging']:
            output['file_logging_path'] = os.path.expanduser(answers.get('file_logging_path'))

        if answers['default workspace'] != self.KEEP_TOGGLS_DEFAULT_WORKSPACE:
            from toggl.api import Workspace
            config = self._build_tmp_config(api_token=answers['api_token'])
            output['default_wid'] = str(Workspace.objects.get(name=answers['default workspace'], config=config).id)

        return output

    def _convert_credentials_to_api_token(self, username, password):  # type: (str, str) -> str
        config = self._build_tmp_config(username=username, password=password)

        data = toggl("/me", "get", config=config)
        return data['data']['api_token']

    def _get_api_token(self):  # type: () -> Union[str, None]
        type_auth = inquirer.shortcuts.list_input(message="Type of authentication you want to use",
                                                  choices=[self.API_TOKEN_OPTION, self.CREDENTIALS_OPTION])

        if type_auth is None:
            return None

        if type_auth == self.API_TOKEN_OPTION:
            return inquirer.shortcuts.password(message="Your API token",
                                               validate=lambda answers, current: self._are_credentials_valid(
                                                   api_token=current))

        questions = [
            inquirer.Text('username', message="Your Username"),
            inquirer.Password('password', message="Your Password"),
        ]

        while True:
            credentials = inquirer.prompt(questions)

            if credentials is None:
                return None

            try:
                return self._convert_credentials_to_api_token(username=credentials['username'],
                                                              password=credentials['password'])
            except exceptions.TogglAuthenticationException:
                click.echo('The provided credentials are not valid! Please try again.')

    def _exit(self):
        click.secho("We were not able to setup the needed configuration and we are unfortunately not able to "
                    "proceed without it.", bg="white", fg="red")
        exit(-1)

    def start(self):
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

        api_token = self._get_api_token()

        if api_token is None:
            self._exit()

        questions = [
            inquirer.List('default workspace', message="Should TogglCli use different default workspace from Toggl's "
                                                       "setting?",
                          choices=lambda answers: self._get_workspaces(api_token)),

            inquirer.Text('timezone', 'Used timezone', default=self.SYSTEM_TIMEZONE,
                          validate=lambda answers, current: current in pendulum.timezones
                                                            or current == self.SYSTEM_TIMEZONE),

            inquirer.Confirm('file_logging', message="Enable logging of togglCli actions into file?", default=False),
            inquirer.Path('file_logging_path', message="Path to the log file", ignore=lambda x: not x['file_logging'],
                          default='~/.toggl_log'),
        ]

        answers = inquirer.prompt(questions)

        if answers is None:
            self._exit()

        click.echo("\nConfiguration successfully finished!\nNow continuing with your command:\n\n")

        return self._map_answers(api_token=api_token, **answers)


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
    datetime_format = 'LTS L'
    day_first = False
    year_first = False
    file_logging = False
    file_logging_path = None
    timezone = None
    use_native_datetime = False

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

        'timezone': IniEntry('options', 'tz'),
        'continue_creates': IniEntry('options', bool),
        'year_first': IniEntry('options', bool),
        'day_first': IniEntry('options', bool),
        'datetime_format': IniEntry('options', str),
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

        :raises exceptions.TogglConfigsException: When no credentials are available.
        :return: requests.auth.HTTPBasicAuth
        """
        try:
            return requests.auth.HTTPBasicAuth(self.api_token, 'api_token')
        except AttributeError:
            pass

        try:
            return requests.auth.HTTPBasicAuth(self.username, self.password)
        except AttributeError:
            raise exceptions.TogglConfigException("There is no authentication configuration!")


class SubCommandsGroup(click.Group):
    """
    Group extension which distinguish between direct commands and groups. Groups
    are then displayed in help as 'Sub-Commands'.
    """

    SUB_COMMANDS_SECTION_TITLE = 'Sub-Commands'

    def __init__(self, *args, **kwargs):
        self.subcommands = {}
        super().__init__(*args, **kwargs)

    def group(self, *args, **kwargs):
        def decorator(f):
            cmd = super(SubCommandsGroup, self).group(*args, **kwargs)(f)
            self.subcommands[cmd.name] = cmd
            return cmd

        return decorator

    def format_subcommands(self, ctx, formatter):
        # Format Sub-Commands
        rows = []
        for subcommand in self.list_subcommands(ctx):
            cmd = self.get_command(ctx, subcommand)
            # What is this, the tool lied about a command.  Ignore it
            if cmd is None:
                continue

            help = cmd.short_help or ''
            rows.append((subcommand, help))

        if rows:
            with formatter.section(self.SUB_COMMANDS_SECTION_TITLE):
                formatter.write_dl(rows)

    def format_commands(self, ctx, formatter):
        self.format_subcommands(ctx, formatter)
        super().format_commands(ctx, formatter)

    def list_subcommands(self, ctx):
        return sorted(self.subcommands)

    def list_commands(self, ctx):
        return sorted(
            {k: v for k, v in self.commands.items() if k not in self.subcommands}
        )


# ----------------------------------------------------------------------------
# toggl
# ----------------------------------------------------------------------------
def handle_error(response):
    if response.status_code == 402:
        raise exceptions.TogglPremiumException(
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
