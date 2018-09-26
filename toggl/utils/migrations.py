import configparser
import logging
import pendulum
import typing
import webbrowser

import click
import inquirer

from .. import exceptions, get_version

logger = logging.getLogger('toggl.utils.config')


class Migration200:

    @staticmethod
    def migrate_authentication(parser):  # type: (configparser.ConfigParser) -> None
        from .others import convert_credentials_to_api_token, are_credentials_valid

        if parser.get('auth', 'prefer_token', fallback='').lower() == 'true':
            parser.has_option('auth', 'username') and parser.remove_option('auth', 'username')
            parser.has_option('auth', 'password') and parser.remove_option('auth', 'password')
        elif parser.get('auth', 'prefer_token', fallback='').lower() == 'false':
            api_token = convert_credentials_to_api_token(
                parser.get('auth', 'username'),
                parser.get('auth', 'password')
            )
            parser.set('auth', 'api_token', api_token)
            parser.remove_option('auth', 'username')
            parser.remove_option('auth', 'password')
        else:
            if not are_credentials_valid(api_token=parser.get('auth', 'api_token')):
                try:
                    api_token = convert_credentials_to_api_token(
                        parser.get('auth', 'username'),
                        parser.get('auth', 'password')
                    )
                    parser.set('auth', 'api_token', api_token)
                except exceptions.TogglAuthenticationException:
                    raise exceptions.TogglConfigMigrationException('Migration 2.0.0: No valid authentication!')

            parser.has_option('auth', 'username') and parser.remove_option('auth', 'username')
            parser.has_option('auth', 'password') and parser.remove_option('auth', 'password')

        parser.has_option('auth', 'prefer_token') and parser.remove_option('auth', 'prefer_token')

    @staticmethod
    def validate_datetime_format(value):
        try:
            pendulum.now().format(value)
            return True
        except ValueError:
            return False

    @staticmethod
    def migrate_datetime(parser):  # type: (configparser.ConfigParser) -> None
        if parser.get('options', 'time_format') == '%I:%M%p':
            parser.set('options', 'datetime_format', 'LTS L')
            return

        while True:
            value = inquirer.shortcuts.text('What datetime format we should use? Type \'doc\' to display format help. Default is based on system\'s locale.',
                                            default='LTS L', validate=lambda _, i: Migration200.validate_datetime_format(i))

            if value == 'doc':
                webbrowser.open('https://pendulum.eustace.io/docs/#tokens')
            else:
                parser.set('options', 'datetime_format', value)
                break

        parser.remove_option('options', 'time_format')

    @staticmethod
    def migrate_timezone(parser):  # type: (configparser.ConfigParser) -> None
        tz = parser.get('options', 'timezone')
        if tz not in pendulum.timezones:
            click.echo('We have not recognized your timezone!')
            new_tz = inquirer.shortcuts.text(
                'Please enter valid timezone. Default is your system\'s timezone.',
                default='local', validate=lambda _, i: i in pendulum.timezones or i == 'local')
            parser.set('options', 'timezone', new_tz)

    @classmethod
    def migrate(cls, parser):  # type: (configparser.ConfigParser) -> configparser.ConfigParser
        cls.migrate_authentication(parser)
        cls.migrate_datetime(parser)
        cls.migrate_timezone(parser)

        parser.remove_option('options', 'continue_creates')

        return parser


class IniConfigMigrator:
    migrations = {
        (2, 0, 0): Migration200
    }

    def __init__(self, store, config_path):  # type: (configparser.ConfigParser, typing.Union[str, typing.TextIO]) -> None
        self.store = store
        self.config_file = config_path

    @staticmethod
    def _should_be_migration_executed(current_version, from_version):
        if current_version[0] > from_version[0]:
            return True

        if current_version[0] >= from_version[0] and current_version[1] > from_version[1]:
            return True

        if current_version[0] >= from_version[0] \
                and current_version[1] >= from_version[1] \
                and current_version[2] > from_version[2]:
            return True

        return False

    def _set_version(self, version):  # type: (tuple) -> None
        if not self.store.has_section('version'):
            self.store.add_section('version')

        verbose_version = self._format_version(version)

        self.store.set('version', 'version', verbose_version)

    def _format_version(self, version, delimiter='.'):  # type: (typing.Tuple[int, int, int], str) -> str
        return delimiter.join(str(e) for e in version)

    def migrate(self, from_version):  # type: (tuple) -> None
        if len(from_version) != 3:
            raise exceptions.TogglConfigException('Unknown format of from_version: \'{}\'! '
                                                  'Tuple with three elements is expected!'.format(from_version))

        something_migrated = False
        for migration_version, migration in self.migrations.items():
            if self._should_be_migration_executed(migration_version, from_version):
                migration.migrate(self.store)
                something_migrated = True

        new_version = get_version(raw=True)
        self._set_version(new_version)

        if isinstance(self.config_file, str):
            with open(self.config_file, 'w') as config_file:
                self.store.write(config_file)
        else:
            self.store.write(self.config_file)

        if something_migrated:
            click.echo('Configuration file was migrated from version {} to {}'.format(
                self._format_version(from_version),
                self._format_version(new_version)
            ))
