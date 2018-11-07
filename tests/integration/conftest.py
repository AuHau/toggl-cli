import pytest
from faker import Faker

from . import helpers


@pytest.fixture()
def fake():
    return Faker()


@pytest.fixture()
def cleanup():
    return helpers.Cleanup


@pytest.fixture(scope='class')
def post_cleanup(request):
    yield  # Do the cleanup after the tests run!

    cls = request.cls
    cls_name = cls.__name__.replace('Test', '').lower()
    cleanup_fnc = getattr(helpers.Cleanup, cls_name)

    if cleanup_fnc is None:
        raise RuntimeError('Unknown class to be cleaned up!')

    cleanup_fnc()


@pytest.fixture()
def cmd():
    return helpers.inner_cmd


@pytest.fixture(scope="session", autouse=True)
def cleanup_all():
    helpers.Cleanup.all()
