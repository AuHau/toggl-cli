import configparser
import logging
import typing

import click

from .. import exceptions, get_version

logger = logging.getLogger('toggl.utils.config')


class Migration200:
    @classmethod
    def migrate(cls, parser):
        pass


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
