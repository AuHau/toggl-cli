import configparser
import logging
import pendulum
import typing
import webbrowser

from pbr import version
import click
import inquirer

from .. import exceptions

logger = logging.getLogger('toggl.utils.config')


class MigrationBase:
    version = None

    @classmethod
    def semantic_version(cls):
        return version.SemanticVersion.from_pip_string(cls.version)


class Migration200b1(MigrationBase):

    version = '2.0.0.0b1'

    @staticmethod
    def migrate_authentication(parser):  # type: (configparser.ConfigParser) -> None
        from .others import convert_credentials_to_api_token, are_credentials_valid

        if parser.get('options', 'prefer_token', fallback='').lower() == 'true':
            parser.has_option('auth', 'username') and parser.remove_option('auth', 'username')
            parser.has_option('auth', 'password') and parser.remove_option('auth', 'password')
        elif parser.get('options', 'prefer_token', fallback='').lower() == 'false':
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
        parser.has_option('options', 'prefer_token') and parser.remove_option('options', 'prefer_token')

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
            parser.set('options', 'time_format', 'LTS')
            return

        while True:
            value = inquirer.shortcuts.text('What datetime format we should use? Type \'doc\' to display format help. '
                                            'Default is based on system\'s locale.',
                                            default='LTS L', validate=lambda _, i: i == 'doc'
                                                                      or Migration200b1.validate_datetime_format(i))

            if value == 'doc':
                webbrowser.open('https://pendulum.eustace.io/docs/#tokens')
            else:
                parser.set('options', 'datetime_format', value)
                break

        while True:
            value = inquirer.shortcuts.text('What time format we should use? Type \'doc\' to display format help. '
                                            'Default is based on system\'s locale.',
                                            default='L', validate=lambda _, i: i == 'doc'
                                                                   or Migration200b1.validate_datetime_format(i))

            if value == 'doc':
                webbrowser.open('https://pendulum.eustace.io/docs/#tokens')
            else:
                parser.set('options', 'datetime_format', value)
                break

    @staticmethod
    def migrate_timezone(parser):  # type: (configparser.ConfigParser) -> None
        tz = parser.get('options', 'timezone')
        if tz not in pendulum.timezones:
            click.echo('We have not recognized your timezone!')
            new_tz = inquirer.shortcuts.text(
                'Please enter valid timezone. Default is your system\'s timezone.',
                default='local', validate=lambda _, i: i in pendulum.timezones or i == 'local')
            parser.set('options', 'tz', new_tz)

    @classmethod
    def migrate(cls, parser):  # type: (configparser.ConfigParser) -> configparser.ConfigParser
        cls.migrate_authentication(parser)
        cls.migrate_datetime(parser)
        cls.migrate_timezone(parser)

        parser.remove_option('options', 'continue_creates')

        return parser


class IniConfigMigrator:
    """
    Class which orchestrate migration of configuration files between versions.
    """

    # List of all migrations, ordered by their version!
    migrations = (
        Migration200b1,
    )

    def __init__(self, store, config_path):  # type: (configparser.ConfigParser, typing.Union[str, typing.TextIO]) -> None
        self.store = store
        self.config_file = config_path

    @classmethod
    def is_migration_needed(cls, config_version):  # type: (version.SemanticVersion) -> bool
        return cls.migrations[-1].semantic_version() > config_version

    def _set_version(self, new_version):  # type: (version.SemanticVersion) -> None
        """
        Method which set a version into the config's file.
        """
        if not self.store.has_section('version'):
            self.store.add_section('version')

        self.store.set('version', 'version', new_version.release_string())

    def migrate(self, config_version):  # type: (version.SemanticVersion) -> None
        """
        Main entry point for running the migration. The starting point of the migration is defined by from_version.
        """
        for migration in self.migrations:
            if migration.semantic_version() > config_version:
                migration.migrate(self.store)

        new_version = self.migrations[-1].semantic_version()
        self._set_version(new_version)

        if isinstance(self.config_file, str):
            with open(self.config_file, 'w') as config_file:
                self.store.write(config_file)
        else:
            self.store.write(self.config_file)

        click.echo('Configuration file was migrated from version {} to {}'.format(
            config_version.release_string(),
            new_version.release_string()
        ))
