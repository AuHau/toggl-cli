import logging
import re
import webbrowser
from collections import Iterable, OrderedDict

import click
import pendulum
from prettytable import PrettyTable

from . import api, exceptions, utils, __version__

DEFAULT_CONFIG_PATH = '~/.togglrc'

logger = logging.getLogger('toggl.cli')


class DateTimeType(click.ParamType):
    """
    Parse a string into datetime object. The parsing utilize `dateutil.parser.parse` function
    which is very error resilient and always returns a datetime object with a best-guess.

    Also special string NOW_STRING is supported which creates datetime with current date and time.
    """
    name = 'datetime'
    NOW_STRING = 'now'

    def __init__(self, allow_now=False):
        self._allow_now = allow_now

    def convert(self, value, param, ctx):
        if value is None:
            return None

        config = ctx.obj.get('config') or utils.Config.factory()

        if value == self.NOW_STRING and self._allow_now:
            return pendulum.now(config.timezone)

        try:
            try:
                return pendulum.parse(value, tz=config.timezone, strict=False, dayfirst=config.day_first,
                                      yearfirst=config.year_first)
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


class ResourceType(click.ParamType):
    """
    Takes an Entity class and based on the type of entered specification searches either
    for ID or Name of the entity
    """
    name = 'resource-type'

    def __init__(self, resource_cls):
        self._resource_cls = resource_cls

    def convert(self, value, param, ctx):
        try:
            resource_id = int(value)
            return self._convert_id(resource_id, param, ctx)
        except ValueError:
            pass

        return self._convert_name(value, param, ctx)

    def _convert_id(self, resource_id, param, ctx):
        resource = self._resource_cls.objects.get(resource_id)

        if resource is None:
            self.fail("Unknown {}'s ID!".format(self._resource_cls.get_name(verbose=True)), param, ctx)

        return resource

    def _convert_name(self, value, param, ctx):
        resource = self._resource_cls.objects.get(name=value)

        if resource is None:
            self.fail("Unknown {}'s name!".format(self._resource_cls.get_name(verbose=True)), param, ctx)

        return resource


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

            if modifier == '+':
                out[field] = None

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


# ----------------------------------------------------------------------------
# NEW CLI
# ----------------------------------------------------------------------------
@click.group(cls=utils.SubCommandsGroup)
@click.option('--quiet', '-q', is_flag=True, help="don't print anything")
@click.option('--verbose', '-v', is_flag=True, help="print additional info")
@click.option('--debug', '-d', is_flag=True, help="print debugging output")
@click.option('--config', type=click.Path(exists=True), envvar='TOGGL_CONFIG',
              help="sets specific Config file to be used (ENV: TOGGL_CONFIG)")
@click.version_option(__version__)
@click.pass_context
def cli(ctx, quiet, verbose, debug, config=None):
    """
    CLI interface to interact with Toggl tracking application.

    This application implements limited subsets of Toggl's functionality.

    Many of the options can be set through Environmental variables. The names of the variables
    are denoted in the option's helps with format "(ENV: <name of variable>)".

    The authentication credentials can be also overridden with Environmental variables. Use
    TOGGL_API_TOKEN or TOGGL_USERNAME, TOGGL_PASSWORD.
    """
    if config is None:
        config = utils.Config.factory()
    else:
        config = utils.Config.factory(config)

    if not config.is_loaded:
        config.cli_bootstrap()
        config.persist()

    ctx.obj['config'] = config

    main_logger = logging.getLogger('toggl')
    main_logger.setLevel(logging.DEBUG)

    default = logging.StreamHandler()
    default_formatter = logging.Formatter('%(levelname)s: %(message)s')
    default.setFormatter(default_formatter)

    if verbose:
        default.setLevel(logging.INFO)
    elif debug:
        default.setLevel(logging.DEBUG)
    else:
        default.setLevel(logging.ERROR)

    if quiet:
        # Is this good idea?
        click.echo = lambda *args, **kwargs: None
    else:
        main_logger.addHandler(default)

    if config.file_logging:
        log_path = config.file_logging_path
        fh = logging.FileHandler(log_path)
        fh_formater = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fh.setFormatter(fh_formater)
        main_logger.addHandler(fh)


@cli.command('www', short_help='open Toggl\'s web client')
def visit_www():
    from .toggl import WEB_CLIENT_ADDRESS
    webbrowser.open(WEB_CLIENT_ADDRESS)


# ----------------------------------------------------------------------------
# Time Entries
# ----------------------------------------------------------------------------
@cli.command('add', short_help='adds finished time entry')
@click.argument('start', type=DateTimeType(allow_now=True))
@click.argument('end', type=DurationType())
@click.argument('descr')
@click.option('--tags', '-a', help='List of tags delimited with \',\'')
@click.option('--project', '-p', envvar="TOGGL_PROJECT", type=ResourceType(api.Project),
              help='Link the entry with specific project. Can be ID or name of the project (ENV: TOGGL_PROJECT)', )
@click.option('--task', '-t', envvar="TOGGL_TASK", type=ResourceType(api.Task),
              help='Link the entry with specific task. Can be ID or name of the task (ENV: TOGGL_TASK)', )
@click.option('--workspace', '-w', envvar="TOGGL_WORKSPACE", type=ResourceType(api.Workspace),
              help='Link the entry with specific workspace. Can be ID or name of the workspace (ENV: TOGGL_WORKSPACE)')
@click.pass_context
def entry_add(ctx, start, end, descr, tags, project, task, workspace):
    """
    Adds finished time entry to Toggl with DESCR description and start
    datetime START which can also be a special string 'now' which denotes current
    datetime. The entry also has END argument which is either specific
    datetime or duration.

    \b
    Duration syntax:
     - 'd' : days
     - 'h' : hours
     - 'm' : minutes
     - 's' : seconds

    Example: 5h 2m 10s - 5 hours 2 minutes 10 seconds from the start time
    """
    if isinstance(end, pendulum.Duration):
        end = start + end

    if tags is not None:
        tags = tags.split(',')

    # Create a time entry.
    entry = api.TimeEntry(
        config=ctx.obj['config'],
        description=descr,
        start=start,
        stop=end,
        task=task,
        tags=tags,
        project=project,
        workspace=workspace
    )

    entry.save()
    click.echo("Time entry '{}' with #{} created.".format(entry.description, entry.id))


@cli.command('ls', short_help='list a time entries')
@click.option('--start', '-s', type=DateTimeType(), help='Defines start of a date range to filter the entries by.')
@click.option('--stop', '-p', type=DateTimeType(), help='Defines stop of a date range to filter the entries by.')
@click.option('--fields', '-f', type=FieldsType(api.TimeEntry), default='description,duration,start,stop',
              help='Defines a set of fields of time entries, which will be displayed. It is also possible to modify default set of fields using \'+\' and/or \'-\' characters. Supported values: billable, description, duration, project, start, stop, tags, created_with')
@click.pass_context
def entry_ls(ctx, start, stop, fields):
    if start is not None or stop is not None:
        entities = api.TimeEntry.objects.filter(start=start, stop=stop, config=ctx.obj['config'])
    else:
        entities = api.TimeEntry.objects.all(config=ctx.obj['config'])

    if not entities:
        click.echo('No entries were found!')
        exit(0)

    table = PrettyTable()
    table.field_names = [click.style(field.capitalize(), fg='white', dim=1) for field in fields]
    table.border = False

    table.align = 'l'
    table.align[click.style('Stop', fg='white', dim=1)] = 'r'
    table.align[click.style('Start', fg='white', dim=1)] = 'r'
    table.align[click.style('Duration', fg='white', dim=1)] = 'r'

    for entity in entities:
        row = []
        for field in fields:
            if field == 'stop':
                value = str(entity.__fields__[field].format(getattr(entity, field), instance=entity,
                                                            display_running=True))
            elif field == 'start':
                value = str(entity.__fields__[field].format(getattr(entity, field), instance=entity,
                                                            only_time_for_same_day=True))
            else:
                value = str(entity.__fields__[field].format(getattr(entity, field)))
            row.append(value)

        table.add_row(row)

    click.echo(table)


@cli.command('rm', short_help='delete a time entry')
@click.argument('spec')
@click.pass_context
def entry_rm(ctx, spec):
    entity_remove(api.TimeEntry, spec, config=ctx.obj['config'])


@cli.command('start', short_help='starts new time entry')
@click.argument('descr', required=False)
@click.option('--start', '-s', type=DateTimeType(allow_now=True), help='Specifies start of the time entry. '
                                                                       'If left empty \'now\' is assumed.')
@click.option('--project', '-p', envvar="TOGGL_PROJECT", type=ResourceType(api.Project),
              help='Link the entry with specific project. Can be ID or name of the project (ENV: TOGGL_PROJECT)', )
@click.option('--workspace', '-w', envvar="TOGGL_WORKSPACE", type=ResourceType(api.Workspace),
              help='Link the entry with specific workspace. Can be ID or name of the workspace (ENV: TOGGL_WORKSPACE)')
@click.pass_context
def entry_start(ctx, descr, start, project, workspace):
    api.TimeEntry.start_and_save(
        config=ctx.obj['config'],
        start=start,
        description=descr,
        project=project,
        workspace=workspace
    )


@cli.command('now', short_help='manage current time entry')
@click.option('--description', '-d', help='Sets description')
@click.option('--start', '-s', type=DateTimeType(allow_now=True), help='Sets starts time.')
@click.option('--project', '-p', envvar="TOGGL_PROJECT", type=ResourceType(api.Project),
              help='Link the entry with specific project. Can be ID or name of the project (ENV: TOGGL_PROJECT)', )
@click.option('--workspace', '-w', envvar="TOGGL_WORKSPACE", type=ResourceType(api.Workspace),
              help='Link the entry with specific workspace. Can be ID or name of the workspace (ENV: TOGGL_WORKSPACE)')
@click.pass_context
def entry_now(ctx, **kwargs):
    current = api.TimeEntry.objects.current(config=ctx.obj['config'])

    if current is None:
        click.echo('There is no time entry running!')
        exit(1)

    updated = False
    for key, value in kwargs.items():
        if value is not None:
            updated = True
            setattr(current, key, value)

    if updated:
        current.save()

    entity_detail(api.TimeEntry, current, primary_field='description', config=ctx.obj['config'])


@cli.command('stop', short_help='stops current time entry')
@click.option('--stop', '-p', type=DateTimeType(allow_now=True), help='Sets stop time.')
@click.pass_context
def entry_stop(ctx, stop):
    current = api.TimeEntry.objects.current(config=ctx.obj['config'])

    if current is None:
        click.echo('There is no time entry running!')
        exit(1)

    current.stop_and_save(stop)

    click.echo('\'{}\' was stopped'.format(current.description))


@cli.command('continue', short_help='continue a time entry')
@click.argument('descr', required=False, type=ResourceType(api.TimeEntry))
@click.option('--start', '-s', type=DateTimeType(), help='Sets a start time.')
@click.pass_context
def entry_continue(ctx, descr, start):
    try:
        if descr is None:
            entry = api.TimeEntry.objects.all(config=ctx.obj['config'])[0]
        else:
            entry = api.TimeEntry.objects.filter(contain=True, description=descr, config=ctx.obj['config'])[0]
    except IndexError:
        click.echo('You don\'t have any time entries in past 9 days!')
        exit(1)

    entry.continue_and_save(start=start)

    click.echo('Time entry \'{}\' continue!'.format(entry.description))


# ----------------------------------------------------------------------------
# Clients
# ----------------------------------------------------------------------------

@cli.group('clients', short_help='clients management')
@click.pass_context
def clients(ctx):
    pass


@clients.command('add', short_help='create new client')
@click.option('--name', '-n', prompt='Name of the client',
              help='Specifies the name of the client', )
@click.option('--notes', help='Specifies a note linked to the client', )
@click.option('--workspace', '-w', envvar="TOGGL_WORKSPACE", type=ResourceType(api.Workspace),
              help='Specifies a workspace where the client will be created. Can be ID or name of the workspace '
                   '(ENV: TOGGL_WORKSPACE)')
@click.pass_context
def clients_add(ctx, name, note, workspace):
    client = api.Client(
        name=name,
        workspace=workspace,
        notes=note,
        config=ctx.obj['config']
    )

    client.save()
    click.echo("Client '{}' with #{} created.".format(client.name, client.id))


@clients.command('update', short_help='update a client')
@click.argument('spec')
@click.option('--name', '-n', help='Specifies the name of the client', )
@click.option('--notes', help='Specifies a note linked to the client', )
@click.pass_context
def clients_update(ctx, spec, **kwargs):
    entity_update(api.Client, spec, config=ctx.obj['config'], **kwargs)


@clients.command('ls', short_help='list clients')
@click.pass_context
def clients_ls(ctx):
    entity_listing(api.Client, config=ctx.obj['config'])


@clients.command('get', short_help='retrieve details of a client')
@click.argument('spec')
@click.pass_context
def clients_get(ctx, spec):
    entity_detail(api.Client, spec, config=ctx.obj['config'])


@clients.command('rm', short_help='delete a specific client')
@click.argument('spec')
@click.pass_context
def clients_rm(ctx, spec):
    entity_remove(api.Client, spec, config=ctx.obj['config'])


# ----------------------------------------------------------------------------
# Projects
# ----------------------------------------------------------------------------
@cli.group('projects', short_help='projects management')
@click.pass_context
def projects(ctx):
    pass


@projects.command('add', short_help='create new project')
@click.option('--name', '-n', prompt='Name of the project',
              help='Specifies the name of the project', )
@click.option('--client', '-c', envvar="TOGGL_CLIENT", type=ResourceType(api.Client),
              help='Specifies a client to which the project will be assigned to. Can be ID or name of the client ('
                   'ENV: TOGGL_CLIENT)')
@click.option('--workspace', '-w', envvar="TOGGL_WORKSPACE", type=ResourceType(api.Workspace),
              help='Specifies a workspace where the project will be created. Can be ID or name of the workspace (ENV: '
                   'TOGGL_WORKSPACE)')
@click.option('--public', '-p', is_flag=True, help='Specifies whether project is accessible for all workspace users ('
                                                   '=public) or just only project\'s users.')
@click.option('--billable/--no-billable', default=True, help='Specifies whether project is billable or not. '
                                                             '(Premium only)')
@click.option('--auto-estimates/--no-auto-estimates', default=False,
              help='Specifies whether the estimated hours are automatically calculated based on task estimations or manually fixed based on the value of \'estimated_hours\' ')
@click.option('--rate', '-r', type=click.FLOAT, help='Hourly rate of the project (Premium only)')
@click.option('--color', type=click.INT, help='ID of color used for the project')
@click.pass_context
def projects_add(ctx, name, client, workspace, public, billable, auto_estimates, rate, color):
    project = api.Project(
        name=name,
        workspace=workspace,
        customer=client,
        is_private=not public,
        billable=billable,
        auto_estimates=auto_estimates,
        color=color,
        rate=rate,
        config=ctx.obj['config']
    )

    project.save()
    click.echo("Project '{}' with #{} created.".format(project.name, project.id))


@projects.command('update', short_help='update a project')
@click.argument('spec')
@click.option('--name', '-n', help='Specifies the name of the project', )
@click.option('--customer', '-c', type=ResourceType(api.Client),
              help='Specifies a client to which the project will be assigned to. Can be ID or name of the client')
@click.option('--public/--no-public', default=None, help='Specifies whether project is accessible for all workspace'
                                                         ' users (=public) or just only project\'s users.')
@click.option('--billable/--no-billable', default=None, help='Specifies whether project is billable or not.'
                                                             ' (Premium only)')
@click.option('--auto-estimates/--no-auto-estimates', default=None,
              help='Specifies whether the estimated hours are automatically calculated based on task estimations or'
                   ' manually fixed based on the value of \'estimated_hours\'')
@click.option('--rate', '-r', type=click.FLOAT, help='Hourly rate of the project (Premium only)')
@click.option('--color', type=click.INT, help='ID of color used for the project')
@click.pass_context
def projects_update(ctx, spec, **kwargs):
    entity_update(api.Project, spec, config=ctx.obj['config'], **kwargs)


@projects.command('ls', short_help='list projects')
@click.pass_context
def projects_ls(ctx):
    entity_listing(api.Project, config=ctx.obj['config'])


@projects.command('get', short_help='retrieve details of a project')
@click.argument('spec')
@click.pass_context
def projects_get(ctx, spec):
    entity_detail(api.Project, spec, config=ctx.obj['config'])


@projects.command('rm', short_help='delete a specific client')
@click.argument('spec')
@click.pass_context
def projects_rm(ctx, spec):
    entity_remove(api.Project, spec, config=ctx.obj['config'])


# ----------------------------------------------------------------------------
# Workspaces
# ----------------------------------------------------------------------------
# TODO: Leave workspace
# TODO: Create workspace

@cli.group('workspaces', short_help='workspaces management')
@click.pass_context
def workspaces(ctx):
    pass


@workspaces.command('ls', short_help='list workspaces')
@click.pass_context
def workspaces_ls(ctx):
    entity_listing(api.Workspace, config=ctx.obj['config'])


@workspaces.command('get', short_help='retrieve details of a workspace')
@click.argument('spec')
@click.pass_context
def workspaces_get(ctx, spec):
    entity_detail(api.Workspace, spec, config=ctx.obj['config'])


# ----------------------------------------------------------------------------
# Tasks
# ----------------------------------------------------------------------------

@cli.group('tasks', short_help='tasks management')
@click.pass_context
def tasks(ctx):
    pass


@tasks.command('add', short_help='create new task')
@click.option('--name', '-n', prompt='Name of the task',
              help='Specifies the name of the task', )
@click.option('--estimated_seconds', '-e', type=click.INT, help='Specifies estimated duration for the task in seconds')
@click.option('--active/--no-active', default=True, help='Specifies whether the task is active', )
@click.option('--workspace', '-w', envvar="TOGGL_WORKSPACE", type=ResourceType(api.Workspace),
              help='Specifies a workspace where the client will be created. Can be ID or name of the workspace '
                   '(ENV: TOGGL_WORKSPACE)')
@click.option('--project', '-p', prompt='Name or ID of project to have the task assigned to', envvar="TOGGL_PROJECT", type=ResourceType(api.Project),
              help='Specifies a project to which the task will be linked to. Can be ID or name of the project '
                   '(ENV: TOGGL_PROJECT)')
@click.option('--user', '-u', envvar="TOGGL_USER", type=ResourceType(api.User),
              help='Specifies a user to whom the task will be assigned. Can be ID or name of the user '
                   '(ENV: TOGGL_USER)')
@click.pass_context
def tasks_add(ctx, **kwargs):
    task = api.Task(config=ctx.obj['config'], **kwargs)

    try:
        task.save()
    except exceptions.TogglPremiumException:
        click.echo("Task was not possible to create as the assigned workspace '{}' is not a Premium workspace!."
                   .format(task.workspace))
        exit(1)

    click.echo("Task '{}' with #{} created.".format(task.name, task.id))


@tasks.command('update', short_help='update a task')
@click.argument('spec')
@click.option('--name', '-n', help='Specifies the name of the task', )
@click.option('--estimated_seconds', '-e', type=click.INT, help='Specifies estimated duration for the task in seconds')
@click.option('--active/--no-active', default=True, help='Specifies whether the task is active', )
@click.option('--user', '-u', envvar="TOGGL_USER", type=ResourceType(api.User),
              help='Specifies a user to whom the task will be assigned. Can be ID or name of the user '
                   '(ENV: TOGGL_USER)')
@click.pass_context
def tasks_update(ctx, spec, **kwargs):
    entity_update(api.Task, spec, config=ctx.obj['config'], **kwargs)


@tasks.command('ls', short_help='list tasks')
@click.pass_context
def tasks_ls(ctx):
    entity_listing(api.Task, config=ctx.obj['config'])


@tasks.command('get', short_help='retrieve details of a task')
@click.argument('spec')
@click.pass_context
def tasks_get(ctx, spec):
    entity_detail(api.Task, spec, config=ctx.obj['config'])


@tasks.command('rm', short_help='delete a specific task')
@click.argument('spec')
@click.pass_context
def tasks_rm(ctx, spec):
    entity_remove(api.Task, spec, config=ctx.obj['config'])


# ----------------------------------------------------------------------------
# Users
# ----------------------------------------------------------------------------
@cli.group('users', short_help='users management')
@click.pass_context
def users(ctx):
    pass


@users.command('ls', short_help='list users for given workspace')
@click.pass_context
def users_ls(ctx):
    entity_listing(api.User, ('id', 'email', 'fullname'), config=ctx.obj['config'])


@users.command('get', short_help='retrieve details of a user')
@click.argument('spec')
@click.pass_context
def users_get(ctx, spec):
    entity_detail(api.User, spec, ('id', 'email', 'fullname'), 'email', config=ctx.obj['config'])


@users.command('signup', short_help='sign up a new user')
@click.option('--email', '-e', help='Email address which represents the new user\'s account',
              prompt='Email of the user to sign up')
@click.option('--password', '-p', help='Password for the new user\'s account', hide_input=True,
              confirmation_prompt=True, prompt='Password of a user to sign up')
@click.option('--timezone', '-t', help='Timezone which will be used for all date/time operations')
@click.option('--created-with', '-c', help='Information about which application created the user\' account')
@click.pass_context
def users_signup(ctx, email, password, timezone=None, created_with=None):
    user = api.User.signup(email, password, timezone, created_with, config=ctx.obj['config'])

    click.echo("User '{}' was successfully created with ID #{}.".format(email, user.id))


# ----------------------------------------------------------------------------
# Workspace users
# ----------------------------------------------------------------------------
@cli.group('workspace_users', short_help='workspace\'s users management (eq. access management for the workspace)')
@click.pass_context
def workspace_users(ctx):
    pass


@workspace_users.command('ls', short_help='list workspace\'s users')
@click.pass_context
def workspace_users_ls(ctx):
    entity_listing(api.WorkspaceUser, ('id', 'email', 'active', 'admin'), config=ctx.obj['config'])


@workspace_users.command('get', short_help='retrieve details of a user')
@click.argument('spec')
@click.pass_context
def workspace_users_get(ctx, spec):
    entity_detail(api.WorkspaceUser, spec, ('id', 'email'), 'email', config=ctx.obj['config'])


@workspace_users.command('invite', short_help='invite new user into workspace')
@click.option('--email', '-e', help='Email address where will be the invite to the worspace send',
              prompt='Email of a user to invite to the workspace')
@click.pass_context
def workspace_users_invite(ctx, email):
    api.WorkspaceUser.invite(email, config=ctx.obj['config'])

    click.echo("User '{}' was successfully invited! He needs to accept the invitation now.".format(email))


@workspace_users.command('rm', short_help='delete a specific workspace\'s user')
@click.argument('spec')
@click.pass_context
def workspace_users_rm(ctx, spec):
    entity_remove(api.WorkspaceUser, spec, ('id', 'email'), config=ctx.obj['config'])


@workspace_users.command('update', short_help='update a specific workspace\'s user')
@click.argument('spec')
@click.option('--admin/--no-admin', default=None,
              help='Specifies if the workspace\'s user is admin for the workspace', )
@click.pass_context
def workspace_users_update(ctx, spec, **kwargs):
    entity_update(api.WorkspaceUser, spec, ('id', 'email'), config=ctx.obj['config'], **kwargs)
