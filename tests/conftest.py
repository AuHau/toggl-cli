from pathlib import Path
import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        if item.fspath is None:
            continue

        if 'integration' in str(item.fspath):
            item.add_marker(pytest.mark.integration)

        if 'unit' in str(item.fspath):
            item.add_marker(pytest.mark.unit)


@pytest.fixture(scope="session", autouse=True)
def set_default_config(session_mocker):
    from toggl.utils import config

    session_mocker.patch.object(config.IniConfigMixin, 'DEFAULT_CONFIG_PATH',
                                new_callable=session_mocker.PropertyMock(
                                    return_value=str(Path(__file__) / 'configs' / 'non-premium.config')
                                ))
    print(config.IniConfigMixin.DEFAULT_CONFIG_PATH)

    yield
    session_mocker.stopall()
