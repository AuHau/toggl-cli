import configparser
import logging
import os
import typing
from collections import namedtuple
from pprint import pprint

import requests

from . import metas, bootstrap, migrations
from .. import exceptions, get_version

logger = logging.getLogger('toggl.utils.config')

# Defines which attrs of all parents will be merged into the new config class -> related to ConfigMeta
MERGE_ATTRS = ('INI_MAPPING', 'ENV_MAPPING')


class ConfigMeta(metas.CachedFactoryMeta, metas.ClassAttributeModificationWarning):
    """
    Meta class which implements merging of defined attrs from base classes into the new one.
    See MERGE_ATTRS.
    """

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
    """
    Class mixin for implementing __getattribute__ which have a source of a data in config file that is implemented
    using ConfigParser.

    INI_MAPPING defines mapping of config (ini) file structure (eq. sections -> options) into just attribute's names.
    It also defines the types of the values for correct type casting.

    Only attributes that have entry in INI_MAPPING will be considered during the lookup, if the attribute does not have
    entry the look continues with propagating the lookup to next in line, with super().
    """
    INI_MAPPING = {
        'version': IniEntry('version', str),
    }

    DEFAULT_CONFIG_PATH = os.path.expanduser('~/.togglrc')

    def __init__(self, config_path=sentinel, **kwargs):  # type: (str, **typing.Any) -> None
        self._config_path = self.DEFAULT_CONFIG_PATH if config_path == sentinel else config_path
        self._store = configparser.ConfigParser(interpolation=None)
        self._loaded = False

        if self._config_path is not None:
            self._loaded = self._store.read(self._config_path)

            if self._need_migrate():
                migrator = migrations.IniConfigMigrator(self._store, self._config_path)
                migrator.migrate(self._get_version(raw=True))

        super().__init__(**kwargs)

    def _need_migrate(self):  # type: () -> bool
        """
        Method checks whether the current config needs to migrate.
        """
        return self._loaded and self._get_version() != get_version()

    def _get_version(self, raw=False):  # type: (bool) -> typing.Union[str, tuple]
        """
        Method get version of the current config.
        It can return the version as semver string or parsed tuple.
        """
        version = self._get('version')

        # Version 1.0 of TogglCLI
        if version is None:
            if raw:
                return 1, 0, 0

            return '1.0.0'

        if raw:
            return version.split('.')

        return version

    def _resolve_type(self, entry, item):  # type: (IniEntry, str) -> typing.Any
        """
        Method returns value in config file defined by entry.section and item (eq. option).
        The value is type-casted into proper type defined in the entry.type.
        """
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

    def _get(self, item):  # type: (str) -> typing.Any
        """
        Method return config's value defined by property name 'item'.
        """
        mapping_dict = object.__getattribute__(self, 'INI_MAPPING')
        return self._resolve_type(mapping_dict.get(item), item)

    def __getattribute__(self, item):  # type: (str) -> typing.Any
        """
        Attr lookup method which implements the main logic.
        """
        mapping_dict = object.__getattribute__(self, 'INI_MAPPING')
        if item in mapping_dict:
            value = self._resolve_type(mapping_dict[item], item)
            if value is not None:
                return value

        return super(IniConfigMixin, self).__getattribute__(item)

    @property
    def is_loaded(self):  # type: () -> bool
        """
        Method states if the config file associated with this config's instance was loaded. Eq. if the file exists,
        is readable and was loaded into memory.
        """
        return bool(self._loaded)

    def persist(self, items=None):  # type: (dict) -> None
        """
        Method persists the Config's values which are related to IniConfigMixin (eq. are defined in the INI_MAPPING)
        into config's file.
        """
        if self._config_path is None or items is None:
            return

        for item, value in items.items():
            if item in self.INI_MAPPING:
                section = self.INI_MAPPING[item].section

                if not self._store.has_section(section):
                    self._store.add_section(section)

                if value is None:
                    self._store.remove_option(section, item)
                else:
                    self._store.set(section, item, str(value))

        with open(self._config_path, 'w') as config_file:
            self._store.write(config_file)


EnvEntry = namedtuple('EnvEntry', ['variable', 'type'])


class EnvConfigMixin:
    """
    Class mixin for implementing __getattribute__ which have a source of a data in environment's variables, where
    mapping between the env variables and config's attributes is specified in ENV_MAPPING.

    Only attributes that have entry in ENV_MAPPING will be considered during the lookup, if the attribute does not have
    entry the look continues with propagating the lookup to next in line, with super().
    """

    ENV_MAPPING = {}

    def __init__(self, read_env=True, **kwargs):  # type: (bool, **typing.Any) -> None
        self._read_env = read_env
        super(EnvConfigMixin, self).__init__(**kwargs)

    def _resolve_variable(self, entry):  # type: (EnvEntry) -> typing.Any
        """
        Method returns correctly type-casted value of env. variable defined by the entry.
        """
        value = os.environ.get(entry.variable)

        if value is None:
            return None

        return entry.type(value)

    def __getattribute__(self, item):  # type: (str) -> typing.Any
        """
        Attr lookup method which implements the main logic.
        """
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
         1) config instance's dict if value is defined
         2) if associated env variable is present, then the env variable is used
         3) if config file specified and associated ini variable is defined appropriate value is used
         4) class's dict for default fallback
    """

    # Default values
    continue_creates = True
    datetime_format = 'LTS L'
    day_first = False
    year_first = False
    file_logging = False
    file_logging_path = None
    tz = None

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

        'tz': IniEntry('options', 'tz'),
        'continue_creates': IniEntry('options', bool),
        'year_first': IniEntry('options', bool),
        'day_first': IniEntry('options', bool),
        'datetime_format': IniEntry('options', str),
        'default_wid': IniEntry('options', int),
    }

    def __init__(self, config_path=sentinel, read_env=True, **kwargs):  # type: (str, bool, **typing.Any) -> None
        super().__init__(config_path=config_path, read_env=read_env, **kwargs)

        self._user = None
        self._default_workspace = None

        # Validate that only proper attributes are set
        for key, value in kwargs.items():
            if key.isupper() or key[0] == '_':
                raise AttributeError('You can not overload constants (eq. uppercase attributes) and private attributes'
                                     '(eq. variables starting with \'_\')!')

            setattr(self, key, value)

    def __getattribute__(self, item):  # type: (str) -> typing.Any
        """
        Implements hierarchy lookup as described in the class docstring.
        """
        value_exists = True
        retrieved_value = None
        try:
            retrieved_value = object.__getattribute__(self, item)
        except AttributeError:
            value_exists = False

        # We are not interested in special attributes (private attributes or constants, methods)
        # for the hierarchy lookup
        if item.isupper() or item[0] == '_' or (value_exists and callable(retrieved_value)):
            return retrieved_value

        # Retrieved value differs from the class attribute ==> it is instance's value, which has highest priority
        if value_exists and self._get_class_attribute(item) != retrieved_value:
            return retrieved_value

        return super().__getattribute__(item)

    def _get_class_attribute(self, attr):  # type: (str) -> typing.Any
        return self.__class__.__dict__.get(attr)

    def cli_bootstrap(self):  # type: () -> None
        """
        Method which will call ConfigBootstrap and then the retrieved values copy to the Config's instance.
        :return:
        """
        values_dict = bootstrap.ConfigBootstrap().start()
        for key, value in values_dict.items():
            setattr(self, key, value)

    @property
    def user(self):  # type: () -> '..api.User'
        # Cache the User defined by the instance's config
        if self._user is None:
            from ..api import User
            self._user = User.objects.current_user(config=self)

        return self._user

    @property
    def timezone(self):
        return self.tz or self.user.timezone

    @timezone.setter
    def timezone(self, value):
        self.tz = value

    @property
    def default_workspace(self):  # type: () -> '..api.Workspace'
        """
        Method returns user's default workspace
        """
        if self._default_workspace is not None:
            return self._default_workspace

        try:
            from ..api import Workspace
            self._default_workspace = Workspace.objects.get(self.default_wid, config=self)
            return self._default_workspace
        except AttributeError:
            pass

        return self.user.default_workspace

    # noinspection PyAttributeOutsideInit
    @default_workspace.setter
    def default_workspace(self, value):
        from ..api import Workspace

        self._default_workspace = None

        if value is None:
            self.default_wid = None
            return

        if not isinstance(value, Workspace):
            raise TypeError('You have to pass instance of a Workspace!')

        self.default_wid = value.id

    # TODO: Decide if default values should be also persisted for backwards compatibility
    def persist(self, items=None):  # type: (typing.Sequence) -> None
        """
        Method that enables persist the config and its parent's parts (eq. IniConfigMixin saves a file).
        """
        if items is None:
            items = {}
            for item, value in vars(self).items():
                if item.isupper() or item[0] == '_' or (self._get_class_attribute(item) == value and value is not None):
                    continue

                items[item] = value

        super().persist(items)

    def get_auth(self):  # type: () -> requests.auth.HTTPBasicAuth
        """
        Returns HTTPBasicAuth object to be used with request.

        :raises exceptions.TogglConfigsException: When no credentials are available.
        """
        try:
            return requests.auth.HTTPBasicAuth(self.api_token, 'api_token')
        except AttributeError:
            pass

        try:
            return requests.auth.HTTPBasicAuth(self.username, self.password)
        except AttributeError:
            raise exceptions.TogglConfigException("There is no authentication configuration!")
