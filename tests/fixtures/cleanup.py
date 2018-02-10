import pytest

from toggl import api


@pytest.fixture(scope="session", autouse=True)
def toggl_cleanup():
    """
    Setup fixture which cleans the test account before all tests
    :return:
    """
    for entry in api.TimeEntryList():
        entry.delete()
