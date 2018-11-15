import configparser
from collections import namedtuple
from datetime import datetime, timedelta
from unittest.mock import call

import pendulum
import click
import pytest

from toggl.cli import types
from toggl import utils, api


def remove_tz_helper(datetime_object):
    return datetime_object.replace(tzinfo=None)


def datetime_time(hours=None, minutes=None, seconds=None):
    kwargs = {}

    if hours is not None:
        kwargs['hour'] = hours

    if minutes is not None:
        kwargs['minute'] = minutes

    if seconds is not None:
        kwargs['second'] = seconds

    return pendulum.now().replace(microsecond=0, **kwargs)


@pytest.fixture()
def datetime_type():
    return types.DateTimeType()


@pytest.fixture()
def duration_type():
    return types.DateTimeDurationType()


@pytest.fixture()
def config():
    config = utils.Config.factory(None)

    user = api.User()
    user.timezone = 'UTC'
    config._user = user

    return config


Context = namedtuple('Context', ['obj', 'command'])
Context.__new__.__defaults__ = (None,) * len(Context._fields)

datetime_parsing_test_set = (
    ('2017.1.2', pendulum.datetime(2017, 1, 2, 0, 0)),
    ('2017.10.2', pendulum.datetime(2017, 10, 2, 0, 0)),
    ('2.10.2017', pendulum.datetime(2017, 2, 10, 0, 0)),
    ('20.5.2017', pendulum.datetime(2017, 5, 20, 0, 0)),
    ('10:20', datetime_time(10, 20, 0)),
    ('20:20', datetime_time(20, 20, 0)),
    ('10:20 PM', datetime_time(22, 20, 0)),
)


class TestDateTimeType(object):
    @pytest.mark.parametrize(('input', 'expected'), datetime_parsing_test_set)
    def test_parsing(self, datetime_type, input, expected):
        assert remove_tz_helper(datetime_type.convert(input, None, Context({'config': None}))) == remove_tz_helper(expected)

    def test_parsing_error(self, datetime_type):
        with pytest.raises(click.BadParameter):
            datetime_type.convert("some weird format", None, Context({'config': None}))

    def test_now(self):
        datetime_type_without_now = types.DateTimeType(allow_now=False)
        with pytest.raises(click.BadParameter):
            datetime_type_without_now.convert(types.DateTimeType.NOW_STRING, None, Context({'config': None}))

        datetime_type_with_now = types.DateTimeType(allow_now=True)
        assert remove_tz_helper(datetime_type_with_now.convert(types.DateTimeType.NOW_STRING, None, Context({'config': None})).replace(microsecond=0)) \
               == remove_tz_helper(datetime_time())

    def test_config(self, datetime_type, config):
        config.day_first = True
        config.year_first = False
        assert remove_tz_helper(datetime_type.convert("2.10.2017", None, Context({'config': config}))) \
               == remove_tz_helper(pendulum.datetime(2017, 10, 2, 0, 0))

        config.day_first = False
        assert remove_tz_helper(datetime_type.convert("2.10.2017", None, Context({'config': config}))) \
               == remove_tz_helper(datetime(2017, 2, 10, 0, 0))


duration_parsing_test_set = (
    ('1s', pendulum.duration(seconds=1)),
    ('1s1h', pendulum.duration(hours=1, seconds=1)),
    ('1h1s', pendulum.duration(hours=1, seconds=1)),
    ('2h1h1s', pendulum.duration(hours=1, seconds=1)),
    ('1d 2h 1s', pendulum.duration(days=1, hours=2, seconds=1)),
    ('1d 2H 2M 1s', pendulum.duration(days=1, minutes=2, hours=2, seconds=1)),
)


class TestDurationType:

    @pytest.mark.parametrize(('input', 'expected'), duration_parsing_test_set)
    def test_parsing(self, duration_type, config, input, expected):
        assert duration_type.convert(input, None, Context({'config': config})) == expected

    def test_datetime_fallback(self, duration_type, config):
        # fallbacks to datetime parsing, but still no known syntax ==> exception
        with pytest.raises(click.BadParameter):
            duration_type.convert("random string", None, Context({'config': config}))

        assert remove_tz_helper(duration_type.convert("12:12", None, Context({'config': config}))) == remove_tz_helper(datetime_time(12, 12, 0))
        assert remove_tz_helper(duration_type.convert("20.5.2017", None, Context({'config': config}))) == remove_tz_helper(pendulum.datetime(2017, 5, 20, 0, 0))


class TestResourceType:

    def test_default_lookup(self, mocker, config):
        instance_mock = mocker.Mock()
        instance_mock.objects.get.return_value = 'placeholder'

        resource_type = types.ResourceType(instance_mock)
        assert resource_type.convert(10, None, Context({'config': config})) == 'placeholder'
        instance_mock.objects.get.assert_called_once_with(id=10)
        instance_mock.reset_mock()

        # When nothing is found BadParameter is raised
        instance_mock.objects.get.return_value = None
        with pytest.raises(click.BadParameter):
            resource_type.convert(10, None, Context({'config': config}))

        # Default lookup is ID and Name
        instance_mock.objects.get.assert_has_calls([call(id=10), call(name=10)])

    def test_custom_lookup(self, mocker, config):
        instance_mock = mocker.Mock()
        instance_mock.objects.get.return_value = 'placeholder'

        resource_type = types.ResourceType(instance_mock, fields=('id', 'email', 'test'))
        assert resource_type.convert('asdf', None, Context({'config': config})) == 'placeholder'
        instance_mock.objects.get.assert_called_once_with(email='asdf')
        instance_mock.reset_mock()

        # When nothing is found BadParameter is raised
        instance_mock.objects.get.return_value = None
        with pytest.raises(click.BadParameter):
            resource_type.convert(123, None, Context({'config': config}))

        instance_mock.objects.get.assert_has_calls([call(id=123), call(email=123), call(test=123)])
