import configparser
from collections import namedtuple
from datetime import datetime

import click
import pytest as pytest
import pytz

from toggl import cli


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