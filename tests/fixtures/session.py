import os
import pytest

from toggl import api, utils


@pytest.fixture(scope="session", autouse=True)
def toggl_cleanup():
    """
    Setup fixture which cleans the test account before all tests
    :return:
    """
    for entry in api.TimeEntryList():
        entry.delete()


@pytest.fixture(scope="class", autouse=True)
def tests_debug():
    """
    Sets Logger level to the content of env variable LOGGER_LEVEL if present
    :return:
    """
    level_map = {
        'debug': utils.Logger.DEBUG,
        'info': utils.Logger.INFO,
    }

    input_level = os.environ.get("LOGGER_LEVEL", "").lower()

    utils.Logger.level = level_map.get(input_level, utils.Logger.NONE)
