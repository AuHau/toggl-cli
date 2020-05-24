import logging
import os
import pathlib
import re
import typing
from collections.abc import Iterable

import click
import pendulum
from notifypy import Notify
from prettytable import PrettyTable

from toggl.api import base
from toggl.cli.themes import themes

logger = logging.getLogger('toggl.cli')


def entity_listing(cls, fields=('id', 'name',), obj=None):  # type: (typing.Union[typing.Sequence, base.Entity], typing.Sequence, dict) -> None
    config = obj.get('config')
    workspace = obj.get('workspace')
    theme = themes.get(config.theme)

    entities = cls if isinstance(cls, Iterable) else cls.objects.all(config=config, workspace=workspace)
    if not entities:
        click.echo('No entries were found!')
        exit(0)

    if obj.get('simple'):
        if obj.get('header'):
            click.echo('\t'.join([click.style(field.capitalize(), **theme.header) for field in fields]))

        for entity in entities:
            click.echo('\t'.join([str(entity.__fields__[field].format(getattr(entity, field, ''))) for field in fields]))
        return

    table = PrettyTable()
    table.field_names = [click.style(field.capitalize(), **theme.header) for field in fields]
    table.header = obj.get('header')
    table.border = False
    table.align = 'l'

    for entity in entities:
        table.add_row([str(entity.__fields__[field].format(getattr(entity, field, ''))) for field in fields])

    click.echo(table)


def get_entity(cls, org_spec, field_lookup, multiple=False, workspace=None, config=None):
    for field in field_lookup:
        # If the passed SPEC is not valid value for the field --> skip
        try:
            spec = cls.__fields__[field].parse(org_spec, None)
        except ValueError:
            continue

        conditions = {field: spec}

        if workspace is not None:
            conditions['workspace'] = workspace

        if multiple:
            entities = cls.objects.filter(config=config, **conditions)
            if entities:
                return entities
        else:
            entities = cls.objects.get(config=config, **conditions)
            if entities is not None:
                return entities

    return [] if multiple else None


def entity_detail(cls, spec, field_lookup=('id', 'name',), primary_field='name', obj=None):
    config = obj.get('config')
    workspace = obj.get('workspace')
    theme = themes.get(config.theme)

    entity = spec if isinstance(spec, cls) else get_entity(cls, spec, field_lookup, workspace=workspace, config=config)

    if entity is None:
        click.echo('{} not found!'.format(cls.get_name(verbose=True)), color=theme.error_color)
        exit(44)

    entity_dict = {}
    for field in entity.__fields__.values():
        if field.read:
            entity_dict[field.name] = field.format(getattr(entity, field.name, ''))

    del entity_dict[primary_field]
    del entity_dict['id']

    entity_string = ''
    for key, value in sorted(entity_dict.items()):
        if obj.get('header'):
            entity_string += '\n{}: {}'.format(
                click.style(key.replace('_', ' ').capitalize(), **theme.header),
                '' if value is None else value
            )
        else:
            entity_string += '\n' + str(value)

    click.echo("""{} {}
{}""".format(
        click.style(getattr(entity, primary_field, ''), **theme.title),
        click.style('#' + str(entity.id),  **theme.title_id),
        entity_string[1:]))


def entity_remove(cls, spec, field_lookup=('id', 'name',), obj=None):
    config = obj.get('config')
    workspace = obj.get('workspace')
    theme = themes.get(config.theme)

    entities = get_entity(cls, spec, field_lookup, multiple=True, workspace=workspace, config=config)

    if not entities:
        click.echo('{} not found!'.format(cls.get_name(verbose=True)), color=theme.error_color)
        exit(44)
    elif len(entities) == 1:
        entity = entities[0]
        entity.delete()
        click.echo('{} successfully deleted!'.format(cls.get_name(verbose=True)))
    else:
        click.secho('Your SPEC resulted in {} following entries:'.format(len(entities)), fg=theme.error_color)
        entity_listing(entities, field_lookup, obj=obj)
        click.confirm('Do you really want to to delete all of these entries?', abort=True)

        for entity in entities:
            entity.delete()

        click.echo('Successfully deleted {} entries'.format(len(entities)))


def entity_update(cls, spec, field_lookup=('id', 'name',), obj=None, **kwargs):
    config = obj.get('config')
    workspace = obj.get('workspace')
    theme = themes.get(config.theme)

    entity = spec if isinstance(spec, base.TogglEntity) else get_entity(cls, spec, field_lookup, workspace=workspace, config=config)

    if entity is None:
        click.echo('{} not found!'.format(cls.get_name(verbose=True)), color=theme.error_color)
        exit(44)

    updated = False
    for key, value in kwargs.items():
        if value is not None:
            updated = True
            setattr(entity, key, value)

    if not updated:
        click.echo('Nothing to update for {}!'.format(cls.get_name(verbose=True)))
        exit(0)

    entity.save()

    click.echo('{} successfully updated!'.format(cls.get_name(verbose=True)))


def notify(title, text):
    """ this function will only work on OSX and needs to be extended for other OS
    @title string for notification title
    @text string for notification content """
    notification = Notify()
    notification.title = title
    notification.message = text
    notification.icon = os.path.join(os.path.dirname(__file__), '..', 'assets', 'icon.png')
    notification.send()

"""
Supported units: d = days, h = hours, m = minutes, s = seconds.

Regex matches unique counts per unit (always the last one, so for '1h1m2h', it will parse 2 hours).
Examples of successful matches:
1d 1h 1m 1s
1h 1d 1s
1H 1d 1S
1h1D1s
1000h

TODO: The regex should validate that no duplicates of units are in the string (example: '10h 5h' should not match)
"""
DURATION_SYNTAX_REGEX = r'(?:(\d+)(d|h|m|s)(?!.*\2)\s?)+?'

DURATION_MAPPING = {
    'd': 'days',
    'h': 'hours',
    'm': 'minutes',
    's': 'seconds',
}


def parse_duration_string(value):
    matches = re.findall(DURATION_SYNTAX_REGEX, value, re.IGNORECASE)

    if not matches:
        return False

    base = pendulum.duration()
    for match in matches:
        unit = DURATION_MAPPING[match[1].lower()]

        base += pendulum.duration(**{unit: int(match[0])})

    return base


def format_duration(duration):
    if isinstance(duration, int):
        duration = pendulum.duration(seconds=duration)
    return '{}:{}:{}'.format(duration.hours, duration.minutes, duration.remaining_seconds)
