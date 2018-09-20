import datetime
import logging
import optparse
import os
import re
import sys
from collections import Iterable

import click
import dateutil
from prettytable import PrettyTable

from . import api, utils, __version__

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
            return config.timezone.localize(datetime.datetime.now())

        try:
            try:
                date = dateutil.parser.parse(value, dayfirst=config.day_first, yearfirst=config.year_first)
                return config.timezone.localize(date)
            except ValueError:
                pass
        except AttributeError:
            try:
                date = dateutil.parser.parse(value)
                return config.timezone.localize(date)
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

    def __init__(self, allow_now=False):
        super(DurationType, self).__init__(allow_now)

    def convert(self, value, param, ctx):
        matches = re.findall(self.SYNTAX_REGEX, value, re.IGNORECASE)

        # If nothing matches ==> unknown syntax ==> fallback to DateTime parsing
        if not matches:
            return super(DurationType, self).convert(value, param, ctx)

        base = datetime.timedelta()
        for match in matches:
            unit = self.MAPPING[match[1].lower()]

            base += datetime.timedelta(**{unit: int(match[0])})

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


def entity_listing(cls, fields=('id', 'name',)):
    entities = cls if isinstance(cls, Iterable) else cls.objects.all()
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


def get_entity(cls, org_spec, field_lookup):
    entity = None
    for field in field_lookup:
        try:
            spec = cls.__fields__[field].parse(org_spec)
        except ValueError:
            continue

        entity = cls.objects.get(**{field: spec})

        if entity is not None:
            break

    return entity


def entity_detail(cls, spec, field_lookup=('id', 'name',), primary_field='name'):
    entity = spec if isinstance(spec, cls) else get_entity(cls, spec, field_lookup)

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
            key.replace('_', ' ').capitalize(),
            value
        )

    click.echo("""{} {}
{}""".format(
        click.style(getattr(entity, primary_field) or '', fg="green"),
        click.style('#' + str(entity.id), fg="green", dim=1),
        entity_string[1:]))


def entity_remove(cls, spec, field_lookup=('id', 'name',)):
    entity = get_entity(cls, spec, field_lookup)

    if entity is None:
        click.echo("{} not found!".format(cls.get_name(verbose=True)), color='red')
        exit(1)

    entity.delete()
    click.echo("{} successfully deleted!".format(cls.get_name(verbose=True)))


def entity_update(cls, spec, field_lookup=('id', 'name',), **kwargs):
    entity = get_entity(cls, spec, field_lookup)

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
    if config is not None:
        config = utils.Config.factory(config)
    else:
        config = utils.Config.factory()

    ctx.obj['config'] = config

    if not config.is_loaded:
        config.cli_bootstrap()
        config.persist()

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
        default.setLevel(logging.WARN)

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


# ----------------------------------------------------------------------------
# Time Entries
# ----------------------------------------------------------------------------
@cli.command('add', short_help='adds finished time entry')
@click.argument('start', type=DateTimeType(allow_now=True))
@click.argument('end', type=DurationType())
@click.argument('descr')
@click.option('--project', '-p', envvar="TOGGL_PROJECT", type=ResourceType(api.Project),
              help='Link the entry with specific project. Can be ID or name of the project (ENV: TOGGL_PROJECT)', )
@click.option('--workspace', '-w', envvar="TOGGL_WORKSPACE", type=ResourceType(api.Workspace),
              help='Link the entry with specific workspace. Can be ID or name of the workspace (ENV: TOGGL_WORKSPACE)')
@click.pass_context
def entry_add(ctx, start, end, descr, project, workspace):
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
    if isinstance(end, datetime.timedelta):
        end = start + end

    # Create a time entry.
    entry = api.TimeEntry(
        description=descr,
        start=start,
        stop=end,
        project=project,
        workspace=workspace
    )

    entry.save()


@cli.command('ls', short_help='list a time entries')
@click.option('--start', '-s', type=DateTimeType(), help='Defines start of a date range to filter the entries by.')
@click.option('--stop', '-p', type=DateTimeType(), help='Defines stop of a date range to filter the entries by.')
@click.pass_context
def entry_ls(ctx, start, stop):
    if start is not None or stop is not None:
        entities = api.TimeEntry.objects.filter(start=start, stop=stop)
    else:
        entities = api.TimeEntry.objects.all()

    # noinspection PyTypeChecker
    entity_listing(entities, fields=('description', 'duration', 'start', 'stop', 'project', 'id'))


@cli.command('rm', short_help='delete a time entry')
@click.argument('spec')
@click.pass_context
def entry_rm(ctx, spec):
    entity_remove(api.TimeEntry, spec)


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
    current = api.TimeEntry.objects.current()

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

    entity_detail(api.TimeEntry, current, primary_field='description')


@cli.command('stop', short_help='stops current time entry')
@click.option('--stop', '-p', type=DateTimeType(allow_now=True), help='Sets stop time.')
@click.pass_context
def entry_stop(ctx, stop):
    current = api.TimeEntry.objects.current()

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
            entry = api.TimeEntry.objects.all()[0]
        else:
            entry = api.TimeEntry.objects.filter(contain=True, description=descr)[0]
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
        wid=workspace['id'] if workspace else None,
        notes=note
    )

    client.save()
    click.echo("Client '{}' with #{} created.".format(client.name, client.id))


@clients.command('update', short_help='update a client')
@click.argument('spec')
@click.option('--name', '-n', help='Specifies the name of the client', )
@click.option('--notes', help='Specifies a note linked to the client', )
@click.pass_context
def clients_update(ctx, spec, **kwargs):
    entity_update(api.Client, spec, **kwargs)


@clients.command('ls', short_help='list clients')
@click.pass_context
def clients_ls(ctx):
    entity_listing(api.Client)


@clients.command('get', short_help='retrieve details of a client')
@click.argument('spec')
@click.pass_context
def clients_get(ctx, spec):
    entity_detail(api.Client, spec)


@clients.command('rm', short_help='delete a specific client')
@click.argument('spec')
@click.pass_context
def clients_rm(ctx, spec):
    entity_remove(api.Client, spec)


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
@click.option('--customer', '-c', envvar="TOGGL_CLIENT", type=ResourceType(api.Client),
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
        wid=workspace['id'] if workspace else None,
        cid=client['id'] if client else None,
        is_private=not public,
        billable=billable,
        auto_estimates=auto_estimates,
        color=color,
        rate=rate
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
    entity_update(api.Project, spec, **kwargs)


@projects.command('ls', short_help='list projects')
@click.pass_context
def projects_ls(ctx):
    entity_listing(api.Project)


@projects.command('get', short_help='retrieve details of a project')
@click.argument('spec')
@click.pass_context
def projects_get(ctx, spec):
    entity_detail(api.Project, spec)


@projects.command('rm', short_help='delete a specific client')
@click.argument('spec')
@click.pass_context
def projects_rm(ctx, spec):
    entity_remove(api.Project, spec)


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
    entity_listing(api.Workspace)


@workspaces.command('get', short_help='retrieve details of a workspace')
@click.argument('spec')
@click.pass_context
def workspaces_get(ctx, spec):
    entity_detail(api.Workspace, spec)


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
    entity_listing(api.User, ('id', 'email', 'fullname'))


@users.command('get', short_help='retrieve details of a user')
@click.argument('spec')
@click.pass_context
def users_get(ctx, spec):
    entity_detail(api.User, spec, ('id', 'email', 'fullname'), 'email')


@users.command('signup', short_help='sign up a new user')
@click.option('--email', '-e', help='Email address which represents the new user\'s account',
              prompt='Email of the user to sign up')
@click.option('--password', '-p', help='Password for the new user\'s account', hide_input=True,
              confirmation_prompt=True, prompt='Password of a user to sign up')
@click.option('--timezone', '-t', help='Timezone which will be used for all date/time operations')
@click.option('--created-with', '-c', help='Information about which application created the user\' account')
@click.pass_context
def users_signup(ctx, email, password, timezone=None, created_with=None):
    user = api.User.signup(email, password, timezone, created_with)

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
    entity_listing(api.WorkspaceUser, ('id', 'email', 'active', 'admin'))


@workspace_users.command('get', short_help='retrieve details of a user')
@click.argument('spec')
@click.pass_context
def workspace_users_get(ctx, spec):
    entity_detail(api.WorkspaceUser, spec, ('id', 'email'), 'email')


@workspace_users.command('invite', short_help='invite new user into workspace')
@click.option('--email', '-e', help='Email address where will be the invite to the worspace send',
              prompt='Email of a user to invite to the workspace')
@click.pass_context
def workspace_users_invite(ctx, email):
    api.WorkspaceUser.invite(email)

    click.echo("User '{}' was successfully invited! He needs to accept the invitation now.".format(email))


@workspace_users.command('rm', short_help='delete a specific workspace\'s user')
@click.argument('spec')
@click.pass_context
def workspace_users_rm(ctx, spec):
    entity_remove(api.WorkspaceUser, spec, ('id', 'email'))


@workspace_users.command('update', short_help='update a specific workspace\'s user')
@click.argument('spec')
@click.option('--admin/--no-admin', default=None,
              help='Specifies if the workspace\'s user is admin for the workspace', )
@click.pass_context
def workspace_users_update(ctx, spec, **kwargs):
    entity_update(api.WorkspaceUser, spec, ('id', 'email'), **kwargs)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
class CLI(object):
    """
    Singleton class to process command-line actions.
    """
    __metaclass__ = utils.Singleton

    def __init__(self, args=None):
        """
        Initializes the command-line parser and handles the command-line
        options.
        """

        # Override the option parser epilog formatting rule.
        # See http://stackoverflow.com/questions/1857346/python-optparse-how-to-include-additional-info-in-usage-output
        optparse.OptionParser.format_epilog = lambda opt_self, formatter: opt_self.epilog

        self.parser = optparse.OptionParser(
            usage="Usage: %prog [OPTIONS] [ACTION]",
            epilog="\nActions:\n"
                   "  add DESCR [:WORKSPACE] [@PROJECT] START_DATETIME ('d'DURATION | END_DATETIME)\n"
                   "\tcreates a completed time entry\n"
                   "  add DESCR [:WORKSPACE] [@PROJECT] 'd'DURATION\n"
                   "\tcreates a completed time entry, with start time DURATION ago\n"
                   "  clients\n\tlists all clients\n"
                   "  continue [from DATETIME | 'd'DURATION]\n\trestarts the last entry\n"
                   "  continue DESCR [from DATETIME | 'd'DURATION]\n\trestarts the last entry matching DESCR\n"
                   "  ls\n\tlist recent time entries\n"
                   "  now\n\tprint what you're working on now\n"
                   "  workspaces\n\tlists all workspaces\n"
                   "  projects [:WORKSPACE]\n\tlists all projects\n"
                   "  rm ID\n\tdelete a time entry by id\n"
                   "  start DESCR [:WORKSPACE] [@PROJECT] ['d'DURATION | DATETIME]\n\tstarts a new entry\n"
                   "  stop [DATETIME]\n\tstops the current entry\n"
                   "  www\n\tvisits toggl.com\n"
                   "\n"
                   "  DURATION = [[Hours:]Minutes:]Seconds\n"
        )
        self.parser.add_option("-q", "--quiet",
                               action="store_true", dest="quiet", default=False,
                               help="don't print anything")
        self.parser.add_option("-v", "--verbose",
                               action="store_true", dest="verbose", default=False,
                               help="print additional info")
        self.parser.add_option("-d", "--debug",
                               action="store_true", dest="debug", default=False,
                               help="print debugging output")

        # self.args stores the remaining command line args.
        (options, self.args) = self.parser.parse_args(args)

        # Process command-line options.
        utils.Logger.level = utils.Logger.INFO
        if options.quiet:
            utils.Logger.level = utils.Logger.NONE
        if options.debug:
            utils.Logger.level = utils.Logger.DEBUG
        if options.verbose:
            global VERBOSE
            VERBOSE = True

    def _add_time_entry(self, args):
        """
        Creates a completed time entry.
        args should be: DESCR [:WORKSPACE] [@PROJECT] START_DATE_TIME
            'd'DURATION | STOP_DATE_TIME
        or: DESCR [:WORKSPACE] [@PROJECT] 'd'DURATION
        """
        # Process the args.
        description = self._get_str_arg(args)
        workspace_name = self._get_workspace_arg(args, optional=True)
        ws_name = None  # canonical name from toggl
        if workspace_name is not None:
            workspace = api.WorkspaceList().find_by_name(workspace_name)
            if workspace is None:
                raise RuntimeError("Workspace '{}' not found.".format(workspace_name))
            else:
                ws_name = workspace["name"]
        project_name = self._get_project_arg(args, optional=True)
        if project_name is not None:
            project = api.ProjectList(ws_name).find_by_name(project_name)
            if project is None:
                raise RuntimeError("Project '{}' not found.".format(project_name))

        duration = self._get_duration_arg(args, optional=True)
        if duration is not None:
            start_time = utils.DateAndTime().now() - datetime.timedelta(seconds=duration)
            stop_time = None
        else:
            start_time = self._get_datetime_arg(args, optional=False)
            duration = self._get_duration_arg(args, optional=True)
            if duration is None:
                stop_time = self._get_datetime_arg(args, optional=False)
                duration = (stop_time - start_time).total_seconds()
            else:
                stop_time = None

        # Create a time entry.
        entry = api.TimeEntry(
            description=description,
            start_time=start_time,
            stop_time=stop_time,
            duration=duration,
            project_name=project_name,
            workspace_name=workspace_name
        )

        utils.Logger.debug(entry.json())
        entry.add()
        utils.Logger.info('{} added'.format(description))

    def act(self):
        """
        Performs the actions described by the list of arguments in self.args.
        """
        from .toggl import VISIT_WWW_COMMAND

        if len(self.args) == 0 or self.args[0] == "ls":
            utils.Logger.info(api.TimeEntryList())
        elif self.args[0] == "add":
            self._add_time_entry(self.args[1:])
        elif self.args[0] == "clients":
            print(api.ClientList())
        elif self.args[0] == "continue":
            self._continue_entry(self.args[1:])
        elif self.args[0] == "now":
            self._list_current_time_entry()
        elif self.args[0] == "projects":
            self._show_projects(self.args[1:])
        elif self.args[0] == "rm":
            self._delete_time_entry(self.args[1:])
        elif self.args[0] == "start":
            self._start_time_entry(self.args[1:])
        elif self.args[0] == "stop":
            self._stop_time_entry(self.args[1:])
        elif self.args[0] == "www":
            os.system(VISIT_WWW_COMMAND)
        elif self.args[0] == "workspaces":
            print(api.WorkspaceList())
        else:
            self.print_help()

    def _show_projects(self, args):
        workspace_name = self._get_workspace_arg(args, optional=True)
        print(api.ProjectList(workspace_name))

    def _continue_entry(self, args):
        """
        Continues a time entry. args[0] should be the description of the entry
        to restart. If a description appears multiple times in your history,
        then we restart the newest one.
        """
        if len(args) == 0 or args[0] == "from":
            entry = api.TimeEntryList().get_latest()
        else:
            entry = api.TimeEntryList().find_by_description(args[0])
            args.pop(0)

        if entry:
            continued_at = None
            if len(args) > 0:
                if args[0] == "from":
                    args.pop(0)
                    if len(args) == 0:
                        self._show_continue_usage()
                        return
                    else:
                        duration = self._get_duration_arg(args, optional=True)
                        if duration is not None:
                            continued_at = utils.DateAndTime().now() - datetime.timedelta(seconds=duration)
                        else:
                            continued_at = self._get_datetime_arg(args, optional=True)
                else:
                    self._show_continue_usage()
                    return

            entry.continue_entry(continued_at)

            utils.Logger.info("{} continued at {}".format(entry.get('description'),
                                                          utils.DateAndTime().format_time(
                                                              continued_at or utils.DateAndTime().now())))
        else:
            utils.Logger.info("Did not find '{}' in list of entries.".format(args[0]))

    def _show_continue_usage(self):
        utils.Logger.info("continue usage: \n\tcontinue DESC from START_DATE_TIME | 'd'DURATION"
                          "\n\tcontinue from START_DATE_TIME | 'd'DURATION")

    def _delete_time_entry(self, args):
        """
        Removes a time entry from toggl.
        args must be [ID] where ID is the unique identifier for the time
        entry to be deleted.
        """
        if len(args) == 0:
            CLI().print_help()

        entry_id = args[0]

        for entry in api.TimeEntryList():
            if entry.get('id') == int(entry_id):
                entry.delete()
                utils.Logger.info("Deleting entry " + entry_id)

    def _get_datetime_arg(self, args, optional=False):
        """
        Returns args[0] as a localized datetime object, or None.
        """
        if len(args) == 0:
            if optional:
                return None
            else:
                self.print_help()
        else:
            return utils.DateAndTime().parse_local_datetime_str(args.pop(0))

    def _get_duration_arg(self, args, optional=False):
        """
        Returns args[0] (e.g. 'dHH:MM:SS') as an integer number of
        seconds, or None.
        """
        if len(args) == 0:
            if optional:
                return None
            else:
                self.print_help()
        elif args[0][0] != 'd':
            if optional:
                return None
            else:
                self.print_help()
        else:
            return utils.DateAndTime().duration_str_to_seconds(args.pop(0)[1:])

    def _get_workspace_arg(self, args, optional=False):
        """
        If the first entry in args is a workspace name (e.g., ':workspace')
        then return the name of the workspace, or None.
        """
        if len(args) == 0:
            if optional:
                return None
            else:
                self.print_help()
        elif args[0][0] != ':':
            if optional:
                return None
            else:
                self.print_help()
        else:
            return args.pop(0)[1:]

    def _get_project_arg(self, args, optional=False):
        """
        If the first entry in args is a project name (e.g., '@project')
        then return the name of the project, or None.
        """
        if len(args) == 0:
            if optional:
                return None
            else:
                self.print_help()
        elif args[0][0] != '@':
            if optional:
                return None
            else:
                self.print_help()
        else:
            return args.pop(0)[1:]

    def _get_str_arg(self, args, optional=False):
        """
        Returns the first entry in args as a string, or None.
        """
        if len(args) == 0:
            if optional:
                return None
            else:
                self.print_help()
        else:
            return args.pop(0)

    def _list_current_time_entry(self):
        """
        Shows what the user is currently working on.
        """
        entry = api.TimeEntryList().now()

        if entry is not None:
            utils.Logger.info(str(entry))
        else:
            utils.Logger.info("You're not working on anything right now.")

    def print_help(self):
        """Prints the usage message and exits."""
        self.parser.print_help()
        sys.exit(1)

    def _start_time_entry(self, args):
        """
        Starts a new time entry.
        args should be: DESCR [:WORKSPACE] [@PROJECT] ['d'DURATION | DATETIME]
        """
        description = self._get_str_arg(args, optional=False)
        workspace_name = self._get_workspace_arg(args, optional=True)
        project_name = self._get_project_arg(args, optional=True)
        duration = self._get_duration_arg(args, optional=True)
        if duration is not None:
            start_time = utils.DateAndTime().now() - datetime.timedelta(seconds=duration)
        else:
            start_time = self._get_datetime_arg(args, optional=True)

        # Create the time entry.
        entry = api.TimeEntry(
            description=description,
            start_time=start_time,
            project_name=project_name,
            workspace_name=workspace_name
        )
        entry.start()
        utils.Logger.debug(entry.json())
        friendly_time = utils.DateAndTime().format_time(utils.DateAndTime().parse_iso_str(entry.get('start')))
        utils.Logger.info('{} started at {}'.format(description, friendly_time))

    def _stop_time_entry(self, args):
        """
        Stops the current time entry.
        args contains an optional end time.
        """

        entry = api.TimeEntryList().now()
        if entry is not None:
            if len(args) > 0:
                entry.stop(utils.DateAndTime().parse_local_datetime_str(args[0]))
            else:
                entry.stop()

            utils.Logger.debug(entry.json())
            friendly_time = utils.DateAndTime().format_time(utils.DateAndTime().parse_iso_str(entry.get('stop')))
            utils.Logger.info('"{}" stopped at {} and lasted for {}'.format(entry.get('description'), friendly_time,
                                                                            utils.DateAndTime().elapsed_time(
                                                                                entry.get('duration'))))
        else:
            utils.Logger.info("You're not working on anything right now.")
