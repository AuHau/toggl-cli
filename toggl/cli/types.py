import logging
import re
import typing
from collections import OrderedDict

import click
import pendulum

from .. import utils, exceptions

logger = logging.getLogger('toggl.cli')


class DateTimeType(click.ParamType):
    """
    Parse a string into datetime object. The parsing utilize `dateutil.parser.parse` function
    which is very error resilient and always returns a datetime object with a best-guess.

    Also special string NOW_STRING is supported which creates datetime with current date and time.
    """
    name = 'datetime'
    NOW_STRING = 'now'

    def __init__(self, allow_now=False):  # type: (bool) -> None
        self._allow_now = allow_now

    def convert(self, value, param, ctx):
        if value is None:
            return None

        config = ctx.obj.get('config') or utils.Config.factory()

        if value == self.NOW_STRING and not self._allow_now:
            self.fail('\'now\' support is not allowed!', param, ctx)

        try:
            try:
                return pendulum.parse(value, tz=config.timezone, strict=False, day_first=config.day_first,
                                      year_first=config.year_first)
            except ValueError:
                pass
        except AttributeError:
            try:
                return pendulum.parse(value, tz=config.timezone, strict=False)
            except ValueError:
                pass

        self.fail("Unknown datetime format!", param, ctx)


class DurationType(DateTimeType):
    """
    Parse a duration string. If the provided string does not follow duration syntax
    it fallback to DateTimeType parsing.
    """

    name = 'datetime|duration'

    """
    Supported units: d = days, h = hours, m = minutes, s = seconds.

    Regex matches unique counts per unit (always the last one, so for '1h 1m 2h', it will parse 2 hours).
    Examples of successful matches:
    1d 1h 1m 1s
    1h 1d 1s
    1H 1d 1S
    1h1D1s
    1000h

    TODO: The regex should validate that no duplicates of units are in the string (example: '10h 5h' should not match)
    """
    SYNTAX_REGEX = r'(?:(\d+)(d|h|m|s)(?!.*\2)\s?)+?'

    MAPPING = {
        'd': 'days',
        'h': 'hours',
        'm': 'minutes',
        's': 'seconds',
    }

    def convert(self, value, param, ctx):
        matches = re.findall(self.SYNTAX_REGEX, value, re.IGNORECASE)

        # If nothing matches ==> unknown syntax ==> fallback to DateTime parsing
        if not matches:
            return super().convert(value, param, ctx)

        base = pendulum.duration()
        for match in matches:
            unit = self.MAPPING[match[1].lower()]

            base += pendulum.duration(**{unit: int(match[0])})

        return base


# TODO: Add 'fields' parameter that will specify the lookup fields
class ResourceType(click.ParamType):
    """
    Takes an Entity class and then perform lookup of the resource based on the fields specified.

    By default the lookup is based on ID and Name. It is worth mentioning that extending the field lookup
    set introduces load on the API as every lookup equals to call to API. (Possible problems with throttling)
    """
    name = 'resource-type'

    def __init__(self, resource_cls, fields=('id', 'name')):
        self._resource_cls = resource_cls
        self._fields_lookup = fields

    def convert(self, value, param, ctx):
        for field_name in self._fields_lookup:
            if field_name == 'id':
                try:
                    value = int(value)
                except ValueError as e:
                    continue  # If the value is not Integer, no point to try send it to API

            try:
                obj = self._resource_cls.objects.get(**{field_name: value})

                if obj is not None:
                    return obj
            except exceptions.TogglMultipleResultsException:
                pass

        self.fail("Unknown {} under specification \'{}\'!".format(self._resource_cls.get_name(verbose=True), value), param, ctx)


class FieldsType(click.ParamType):
    """
    Type used for defining list of fields for certain TogglEntity (resources_cls).
    The passed fields are validated according the entity's fields.
    Moreover the type supports diff mode, where it is possible to add or remove fields from
    the default list of the fields, using +/- signs.
    """
    name = 'fields-type'

    def __init__(self, resource_cls):
        self._resource_cls = resource_cls

    def _diff_mode(self, value, param, ctx):
        # Using OrderedDict as OrderedSet (eq. all values are None)
        if param is None:
            out = OrderedDict()
        else:
            out = OrderedDict([(key, None) for key in param.default.split(',')])

        modifier_values = value.split(',')
        for modifier_value in modifier_values:
            modifier = modifier_value[0]

            if modifier != '+' and modifier != '-':
                self.fail('Field modifiers must start with either \'+\' or \'-\' character!')

            field = modifier_value.replace(modifier, '')

            if field not in self._resource_cls.__fields__:
                self.fail("Unknown field '{}'!".format(field), param, ctx)

            # Add field
            if modifier == '+':
                out[field] = None

            # Remove field
            if modifier == '-':
                try:
                    del out[field]
                except KeyError:
                    pass

        return out.keys()

    def convert(self, value, param, ctx):
        if '-' in value or '+' in value:
            return self._diff_mode(value, param, ctx)

        fields = value.split(',')
        out = []
        for field in fields:
            field = field.strip()
            if field not in self._resource_cls.__fields__:
                self.fail("Unknown field '{}'!".format(field), param, ctx)

            out.append(field)

        return out

    @staticmethod
    def format_fields_for_help(cls):
        return ', '.join(cls.__fields__.keys())
