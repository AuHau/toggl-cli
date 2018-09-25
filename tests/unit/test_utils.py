import configparser
import io

import pytest

from toggl import utils


class ConfigFakeFile(io.StringIO):

    def get_configparser(self):
        self.seek(0)  # Read the file from beginning
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_file(self)
        return parser


@pytest.fixture()
def file():
    return ConfigFakeFile()


class TestIniConfigMigrator:
    VERSION_1_0_0 = {'auth': {'username': 'user@example.com',
                              'password': 'toggl_password',
                              'api_token': 'your_api_token'},
                     'options': {'timezone': 'UTC',
                                 'time_format': '%I:%M%p',
                                 'prefer_token': 'true',
                                 'continue_creates': 'true'}}

    def _config_parser_factory(self, version):
        parser = configparser.ConfigParser(interpolation=None)

        if version == '1.0.0':
            parser.read_dict(self.VERSION_1_0_0)
        else:
            raise Exception('Unknown version!')

        return parser

    def test_basic_usage(self, file):  # type: (ConfigFakeFile) -> None
        parser = self._config_parser_factory('1.0.0')
        migrator = utils.IniConfigMigrator(parser, file)
        migrator.migrate((1, 0, 0))

        validation_parser = file.get_configparser()
        assert validation_parser.get('version', 'version') == '2.0.0'
