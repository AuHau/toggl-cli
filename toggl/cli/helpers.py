import logging
from collections import Iterable

import click
from prettytable import PrettyTable

logger = logging.getLogger('toggl.cli')


def entity_listing(cls, fields=('id', 'name',), config=None):
    entities = cls if isinstance(cls, Iterable) else cls.objects.all(config=config)
    if not entities:
        click.echo('No entries were found!')
        exit(0)

    table = PrettyTable()
    table.field_names = [click.style(field.capitalize(), fg='white', dim=1) for field in fields]
    table.border = False
    table.align = 'l'

    for entity in entities:
        table.add_row([str(entity.__fields__[field].format(getattr(entity, field))) for field in fields])

    click.echo(table)


def get_entity(cls, org_spec, field_lookup, config=None):
    entity = None
    for field in field_lookup:
        try:
            spec = cls.__fields__[field].parse(org_spec)
        except ValueError:
            continue

        entity = cls.objects.get(config=config, **{field: spec})

        if entity is not None:
            break

    return entity


def entity_detail(cls, spec, field_lookup=('id', 'name',), primary_field='name', config=None):
    entity = spec if isinstance(spec, cls) else get_entity(cls, spec, field_lookup, config=config)

    if entity is None:
        click.echo("{} not found!".format(cls.get_name(verbose=True)), color='red')
        exit(1)

    entity_dict = {}
    for field in entity.__fields__.values():
        entity_dict[field.name] = field.format(getattr(entity, field.name))

    del entity_dict[primary_field]
    del entity_dict['id']

    entity_string = ''
    for key, value in sorted(entity_dict.items()):
        entity_string += '\n{}: {}'.format(
            click.style(key.replace('_', ' ').capitalize(), fg="white", dim=1),
            value
        )

    click.echo("""{} {}
{}""".format(
        click.style(getattr(entity, primary_field) or '', fg="green"),
        click.style('#' + str(entity.id), fg="green", dim=1),
        entity_string[1:]))


def entity_remove(cls, spec, field_lookup=('id', 'name',), config=None):
    entity = get_entity(cls, spec, field_lookup, config)

    if entity is None:
        click.echo("{} not found!".format(cls.get_name(verbose=True)), color='red')
        exit(1)

    entity.delete()
    click.echo("{} successfully deleted!".format(cls.get_name(verbose=True)))


def entity_update(cls, spec, field_lookup=('id', 'name',), config=None, **kwargs):
    entity = get_entity(cls, spec, field_lookup, config=config)

    if entity is None:
        click.echo("{} not found!".format(cls.get_name(verbose=True)), color='red')
        exit(1)

    updated = False
    for key, value in kwargs.items():
        if value is not None:
            updated = True
            setattr(entity, key, value)

    if not updated:
        click.echo("Nothing to update for {}!".format(cls.get_name(verbose=True)))
        exit(0)

    entity.save()

    click.echo("{} successfully updated!".format(cls.get_name(verbose=True)))