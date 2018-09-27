import configparser
import logging
import os
from collections import namedtuple

import requests

from . import metas, bootstrap, migrations
from .. import exceptions, get_version

logger = logging.getLogger('toggl.utils.config')


MERGE_ATTRS = ('INI_MAPPING', 'ENV_MAPPING')


class ConfigMeta(metas.CachedFactoryMeta, metas.ClassAttributeModificationWarning):

    def __new__(mcs, name, bases, attrs, **kwargs):
        attrs = mcs._merge_attrs(attrs, bases)
        return super().__new__(mcs, name, bases, attrs)

    @staticmethod
    def _merge_attrs(attrs, bases):
        for merging_attr_index in MERGE_ATTRS:
            new_attrs = attrs[merging_attr_index] if merging_attr_index in attrs else {}
            for base in bases:
                if hasattr(base, merging_attr_index):
                    new_attrs.update(getattr(base, merging_attr_index))

            attrs[merging_attr_index] = new_attrs

        return attrs


sentinel = object()

IniEntry = namedtuple('IniEntry', ['section', 'type'])


class IniConfigMixin:
    INI_MAPPING = {
        'version': IniEntry('version', str),
    }

    DEFAULT_CONFIG_PATH = os.path.expanduser('~/.togglrc')

    def __init__(self, config_path=sentinel, **kwargs):
        self._config_path = self.DEFAULT_CONFIG_PATH if config_path == sentinel else config_path
        self._store = configparser.ConfigParser(interpolation=None)
        self._loaded = False

        if self._config_path is not None:
            self._loaded = self._store.read(self._config_path)
            if self._need_migrate():
                migrator = migrations.IniConfigMigrator(self._store, self._config_path)
                migrator.migrate(self._get_version(raw=True))

        super().__init__(**kwargs)

    def _need_migrate(self):
        return self._get_version() != get_version()

    def _get_version(self, raw=False):
        version = self._get('version')

        # Version 1.0 of TogglCLI
        if version is None:
            if raw:
                return 1, 0, 0

            return '1.0.0'

        if raw:
            return version.split('.')

        return version

    def _resolve_type(self, entry, item):
        if entry is None:
            return None

        if entry.type == bool:
            return self._store.getboolean(entry.section, item, fallback=None)
        elif entry.type == int:
            return self._store.getint(entry.section, item, fallback=None)
        elif entry.type == float:
            return self._store.getfloat(entry.section, item, fallback=None)
        else:
            return self._store.get(entry.section, item, fallback=None)

    def _get(self, item):
        mapping_dict = object.__getattribute__(self, 'INI_MAPPING')
        return self._resolve_type(mapping_dict.get(item), item)

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
        if self._config_path is None or items is None:
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


# TODO: Default timezone is similarly like default workspace, saved in Toggl settings --> create support for it
class Config(EnvConfigMixin, IniConfigMixin, metaclass=ConfigMeta):
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
    # TODO: use_native_datetime = False

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
        values_dict = bootstrap.ConfigBootstrap().start()
        for key, value in values_dict.items():
            setattr(self, key, value)

    @property
    def user(self):
        # Cache the User defined by the instance's config
        if self._user is None:
            from ..api import User
            self._user = User.objects.current_user(config=self)

        return self._user

    @property
    def default_workspace(self):
        if self._default_workspace is not None:
            return self._default_workspace

        try:
            from ..api import Workspace
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
