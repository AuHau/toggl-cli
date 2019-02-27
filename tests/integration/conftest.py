import pytest
from faker import Faker

from .. import helpers
from . import factories as factories_module


@pytest.fixture()
def fake():
    return Faker()


@pytest.fixture()
def cleanup():
    return helpers.Cleanup


# NOT SURE IF NEEDED - FULL CLEANUP IN BEGINNING MIGHT BE ENOUGH
#
# @pytest.fixture(scope='class')
# def post_cleanup(request):
#     yield  # Do the cleanup after the tests run!
#
#     cls = request.cls
#     cls_name = cls.__name__.replace('Test', '')
#
#     # Converting Camel case to Snake case
#     s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', cls_name)
#     cls_name = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
#
#     cleanup_fnc = getattr(helpers.Cleanup, cls_name)
#
#     if cleanup_fnc is None:
#         raise RuntimeError('Unknown class to be cleaned up!')
#
#     cleanup_fnc()


@pytest.fixture()
def cmd(request):
    node = request.node

    if node.get_closest_marker('premium'):
        return helpers.wrapper_inner_cmd(config='premium.config')
    else:
        return helpers.wrapper_inner_cmd(config='non-premium.config')


@pytest.fixture()
def factories(request):
    node = request.node

    if node.get_closest_marker('premium'):
        factories_module.module_config = helpers.get_config('premium.config')
    else:
        factories_module.module_config = helpers.get_config('non-premium.config')

    return factories_module


@pytest.fixture()
def config(request):
    node = request.node

    if node.get_closest_marker('premium'):
        return helpers.get_config('premium.config')
    else:
        return helpers.get_config('non-premium.config')


@pytest.fixture(scope="session", autouse=True)
def cleanup_all():
    helpers.Cleanup.all_configs()
