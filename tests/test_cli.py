import configparser
from collections import namedtuple
from datetime import datetime, timedelta

import click
import pytest as pytest
import pytz

from toggl import cli
from toggl.exceptions import TogglCliException


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

    return datetime.now().replace(microsecond=0, **kwargs)


@pytest.fixture()
def datetime_type():
    return cli.DateTimeType()


@pytest.fixture()
def duration_type():
    return cli.DurationType()


Context = namedtuple('Context', ['obj'])


class TestDateTimeType(object):
    def test_normal_parsing(self, datetime_type):
        assert remove_tz_helper(datetime_type.convert("2017.1.2", None, {})) == datetime(2017, 1, 2, 0, 0)
        assert remove_tz_helper(datetime_type.convert("2017.10.2", None, {})) == datetime(2017, 10, 2, 0, 0)
        assert remove_tz_helper(datetime_type.convert("2.10.2017", None, {})) == datetime(2017, 2, 10, 0, 0)
        assert remove_tz_helper(datetime_type.convert("20.5.2017", None, {})) == datetime(2017, 5, 20, 0, 0)
        assert remove_tz_helper(datetime_type.convert("10:20", None, {})) == datetime_time(10, 20, 0)
        assert remove_tz_helper(datetime_type.convert("20:20", None, {})) == datetime_time(20, 20, 0)
        assert remove_tz_helper(datetime_type.convert("10:20 PM", None, {})) == datetime_time(22, 20, 0)

        with pytest.raises(click.BadParameter):
            datetime_type.convert("some weird format", None, {})

    def test_now(self):
        datetime_type_without_now = cli.DateTimeType(allow_now=False)
        with pytest.raises(click.BadParameter):
            datetime_type_without_now.convert("now", None, {})

        datetime_type_with_now = cli.DateTimeType(allow_now=True)
        assert remove_tz_helper(datetime_type_with_now.convert("now", None, {})).replace(microsecond=0) \
               == datetime_time()

    def test_config(self, datetime_type):
        config_dict = {
            'options': {
                'day_first': True,
                'year_first': False
            }
        }

        config = configparser.RawConfigParser()
        config.read_dict(config_dict)

        assert remove_tz_helper(datetime_type.convert("2.10.2017", None, Context({'config': config}))) \
               == datetime(2017, 10, 2, 0, 0)

        config_dict = {
            'options': {
                'day_first': False,
                'year_first': False
            }
        }

        config = configparser.RawConfigParser()
        config.read_dict(config_dict)

        assert remove_tz_helper(datetime_type.convert("2.10.2017", None, Context({'config': config}))) \
               == datetime(2017, 2, 10, 0, 0)


class TestDurationType:

    def test_parsing(self, duration_type):
        assert duration_type.convert("1s", None, {}) == timedelta(seconds=1)
        assert duration_type.convert("1s1h", None, {}) == timedelta(hours=1, seconds=1)
        assert duration_type.convert("1h1s", None, {}) == timedelta(hours=1, seconds=1)
        assert duration_type.convert("2h1h1s", None, {}) == timedelta(hours=1, seconds=1)
        assert duration_type.convert("1d 2h 1s", None, {}) == timedelta(days=1, hours=2, seconds=1)
        assert duration_type.convert("1d 2H 2M 1s", None, {}) == timedelta(days=1, minutes=2, hours=2, seconds=1)

    def test_datetime_fallback(self, duration_type):
        # fallbacks to datetime parsing, but still no known syntax ==> exception
        with pytest.raises(click.BadParameter):
            duration_type.convert("random string", None, {})

        assert remove_tz_helper(duration_type.convert("12:12", None, {})) == datetime_time(12, 12, 0)
        assert remove_tz_helper(duration_type.convert("20.5.2017", None, {})) == datetime(2017, 5, 20, 0, 0)


class TestResourceType:

    def test_by_id(self, mocker):
        instance_mock = mocker.Mock()
        instance_mock.find_by_id.return_value = 'placeholder'
        resource_mock = mocker.MagicMock(return_value=instance_mock)
        resource_mock.__name__ = "MockClass"

        resource_type = cli.ResourceType(resource_mock)
        assert resource_type.convert(10, None, {}) == 'placeholder'

        # When nothing is found BadParameter is raised
        instance_mock.find_by_id.return_value = None
        with pytest.raises(click.BadParameter):
            resource_type.convert(10, None, {})

    def test_by_name(self, mocker):
        instance_mock = mocker.Mock()
        instance_mock.find_by_name.return_value = 'placeholder'
        resource_mock = mocker.MagicMock(return_value=instance_mock)
        resource_mock.__name__ = "MockClass"

        resource_type = cli.ResourceType(resource_mock)
        assert resource_type.convert('asdf', None, {}) == 'placeholder'

        # When nothing is found BadParameter is raised
        instance_mock.find_by_name.return_value = None
        with pytest.raises(click.BadParameter):
            resource_type.convert('asdf', None, {})

    def test_interface_detection(self):
        class Mock:
            def __call__(self, *args, **kwargs):
                return self

        resource_type = cli.ResourceType(Mock)

        with pytest.raises(TogglCliException):
            resource_type.convert(10, None, {})  # find_by_id() fails

        with pytest.raises(TogglCliException):
            resource_type.convert("asd", None, {})  # find_by_name() fails
