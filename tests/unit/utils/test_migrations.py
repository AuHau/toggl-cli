import configparser
import io

import pytest
import pytest_mock
from pbr import version

import toggl
from toggl.utils import migrations
from toggl.utils import others


class ConfigFakeFile(io.StringIO):

    def get_configparser(self):
        self.seek(0)  # Read the file from beginning
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_file(self)
        return parser


def get_dict(parser):  # type: (configparser.ConfigParser) -> dict
    return {s: dict(parser.items(s)) for s in parser.sections()}


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

    def test_basic_usage(self, file, mocker):  # type: (ConfigFakeFile, pytest_mock.MockFixture) -> None
        mocker.patch.object(others, 'toggl')
        others.toggl.return_value = {
            'data': {
                'api_token': 'asdf'
            }
        }

        parser = self._config_parser_factory('1.0.0')
        migrator = migrations.IniConfigMigrator(parser, file)
        migrator.migrate(version.SemanticVersion.from_pip_string('1.0.0'))

        validation_parser = file.get_configparser()
        assert validation_parser.get('version', 'version') == '2.0.0.0b1'
        assert not validation_parser.has_option('options', 'continue_creates')
        assert not validation_parser.has_option('options', 'prefer_token')
        assert not validation_parser.has_option('options', 'username')
