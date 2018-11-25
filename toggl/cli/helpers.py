import logging
import typing
from collections.abc import Iterable

import click
from prettytable import PrettyTable

from ..api import base

logger = logging.getLogger('toggl.cli')


def entity_listing(cls, fields=('id', 'name',), obj=None):  # type: (typing.Union[typing.Sequence, base.Entity], typing.Sequence, dict) -> None
    config = obj.get('config')
    workspace = obj.get('workspace')

    entities = cls if isinstance(cls, Iterable) else cls.objects.all(config=config, workspace=workspace)
    if not entities:
        click.echo('No entries were found!')
        exit(0)

    if obj.get('simple'):
        if obj.get('header'):
            click.echo('\t'.join([click.style(field.capitalize(), fg='white', dim=1) for field in fields]))

        for entity in entities:
            click.echo('\t'.join([str(entity.__fields__[field].format(getattr(entity, field, ''))) for field in fields]))
        return

    table = PrettyTable()
    table.field_names = [click.style(field.capitalize(), fg='white', dim=1) for field in fields]
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

    entity = spec if isinstance(spec, cls) else get_entity(cls, spec, field_lookup, workspace=workspace, config=config)

    if entity is None:
        click.echo('{} not found!'.format(cls.get_name(verbose=True)), color='red')
        exit(44)

    entity_dict = {}
    for field in entity.__fields__.values():
        entity_dict[field.name] = field.format(getattr(entity, field.name, ''))

    del entity_dict[primary_field]
    del entity_dict['id']

    entity_string = ''
    for key, value in sorted(entity_dict.items()):
        if obj.get('header'):
            entity_string += '\n{}: {}'.format(
                click.style(key.replace('_', ' ').capitalize(), fg='white', dim=1),
                '' if value is None else value
            )
        else:
            entity_string += '\n' + str(value)

    click.echo("""{} {}
{}""".format(
        click.style(getattr(entity, primary_field, ''), fg='green'),
        click.style('#' + str(entity.id), fg='green', dim=1),
        entity_string[1:]))


def entity_remove(cls, spec, field_lookup=('id', 'name',), obj=None):
    config = obj.get('config')
    workspace = obj.get('workspace')

    entities = get_entity(cls, spec, field_lookup, multiple=True, workspace=workspace, config=config)

    if not entities:
        click.echo('{} not found!'.format(cls.get_name(verbose=True)), color='red')
        exit(44)
    elif len(entities) == 1:
        entity = entities[0]
        entity.delete()
        click.echo('{} successfully deleted!'.format(cls.get_name(verbose=True)))
    else:
        click.secho('Your SPEC resulted in {} following entries:'.format(len(entities)), fg='red')
        entity_listing(entities, field_lookup, obj=obj)
        click.confirm('Do you really want to to delete all of these entries?', abort=True)

        for entity in entities:
            entity.delete()

        click.echo('Successfully deleted {} entries'.format(len(entities)))


def entity_update(cls, spec, field_lookup=('id', 'name',), obj=None, **kwargs):
    config = obj.get('config')
    workspace = obj.get('workspace')

    entity = spec if isinstance(spec, base.TogglEntity) else get_entity(cls, spec, field_lookup, workspace=workspace, config=config)

    if entity is None:
        click.echo('{} not found!'.format(cls.get_name(verbose=True)), color='red')
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
