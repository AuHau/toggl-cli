from pathlib import Path

import pytest
from pytest_mock import MockFixture

from toggl.utils import config


def pytest_collection_modifyitems(items):
    for item in items:
        if item.fspath is None:
            continue

        if 'integration' in str(item.fspath):
            item.add_marker(pytest.mark.integration)

        if 'unit' in str(item.fspath):
            item.add_marker(pytest.mark.unit)


@pytest.fixture(scope="session", autouse=True)
def set_default_config(pytestconfig):
    mocker = MockFixture(pytestconfig)

    mocker.patch.object(config.IniConfigMixin, 'DEFAULT_CONFIG_PATH')
    config.IniConfigMixin.DEFAULT_CONFIG_PATH.return_value = str(Path(__file__) / 'configs' / 'default.config')

    yield
    mocker.stopall()
