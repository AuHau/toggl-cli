import logging
import webbrowser

import click
import pendulum
from prettytable import PrettyTable

from .. import api, exceptions, utils, __version__
from . import helpers, types

DEFAULT_CONFIG_PATH = '~/.togglrc'

logger = logging.getLogger('toggl.cli.commands')


# TODO: Support for manipulating the user's settings
# TODO: Possibility to activate/change a current workspace
# TODO: Listing commands needs add Workspace option
# TODO: Add confirmation option for deletion of resources

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
    from ..toggl import WEB_CLIENT_ADDRESS
    webbrowser.open(WEB_CLIENT_ADDRESS)


# ----------------------------------------------------------------------------
# Time Entries
# ----------------------------------------------------------------------------
@cli.command('add', short_help='adds finished time entry')
@click.argument('start', type=types.DateTimeType(allow_now=True))
@click.argument('end', type=types.DurationType())
@click.argument('descr')
@click.option('--tags', '-a', help='List of tags delimited with \',\'')
@click.option('--project', '-p', envvar="TOGGL_PROJECT", type=types.ResourceType(api.Project),
              help='Link the entry with specific project. Can be ID or name of the project (ENV: TOGGL_PROJECT)', )
@click.option('--task', '-t', envvar="TOGGL_TASK", type=types.ResourceType(api.Task),
              help='Link the entry with specific task. Can be ID or name of the task (ENV: TOGGL_TASK)', )
@click.option('--workspace', '-w', envvar="TOGGL_WORKSPACE", type=types.ResourceType(api.Workspace),
              help='Link the entry with specific workspace. Can be ID or name of the workspace (ENV: TOGGL_WORKSPACE)')
@click.pass_context
def entry_add(ctx, start, end, descr, tags, project, task, workspace):
    """
    Adds finished time entry to Toggl with DESCR description and start
    datetime START which can also be a special string 'now' that denotes current
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

    # TODO: Add click's type to handle directly
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


# TODO: Make possible to list really all time-entries, not first 1000 in last 9 days
@cli.command('ls', short_help='list a time entries')
@click.option('--start', '-s', type=types.DateTimeType(), help='Defines start of a date range to filter the entries by.')
@click.option('--stop', '-p', type=types.DateTimeType(), help='Defines stop of a date range to filter the entries by.')
@click.option('--fields', '-f', type=types.FieldsType(api.TimeEntry), default='description,duration,start,stop',
              help='Defines a set of fields of time entries, which will be displayed. It is also possible to modify default set of fields using \'+\' and/or \'-\' characters. Supported values: ' + types.FieldsType.format_fields_for_help(api.TimeEntry))
@click.pass_context
def entry_ls(ctx, start, stop, fields):
    """
    Lists time entries the user has access to.

    The list is limited with 1000 entries in last 9 days.
    """
    # Limit the list of TimeEntries based on start/stop dates.
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
    """
    Deletes a time entry specified by SPEC argument.

    SPEC argument can be either ID or Description of the Time Entry.
    In case multiple time entries are found, you will be prompted to confirm your deletion.
    """
    helpers.entity_remove(api.TimeEntry, spec, ('id', 'description'), config=ctx.obj['config'])


@cli.command('start', short_help='starts new time entry')
@click.argument('descr', required=False)
@click.option('--start', '-s', type=types.DateTimeType(allow_now=True), help='Specifies start of the time entry. '
                                                                             'If left empty \'now\' is assumed.')
@click.option('--project', '-p', envvar="TOGGL_PROJECT", type=types.ResourceType(api.Project),
              help='Link the entry with specific project. Can be ID or name of the project (ENV: TOGGL_PROJECT)', )
@click.option('--workspace', '-w', envvar="TOGGL_WORKSPACE", type=types.ResourceType(api.Workspace),
              help='Link the entry with specific workspace. Can be ID or name of the workspace (ENV: TOGGL_WORKSPACE)')
@click.pass_context
def entry_start(ctx, descr, start, project, workspace):
    """
    Starts a new time entry with description DESCR (it can be left out). If there is another currently running entry,
    the entry will be stopped and new entry started.
    """
    api.TimeEntry.start_and_save(
        config=ctx.obj['config'],
        start=start,
        description=descr,
        project=project,
        workspace=workspace
    )


@cli.command('now', short_help='manage current time entry')
@click.option('--description', '-d', help='Sets description')
@click.option('--start', '-s', type=types.DateTimeType(allow_now=True), help='Sets starts time.')
@click.option('--project', '-p', envvar="TOGGL_PROJECT", type=types.ResourceType(api.Project),
              help='Link the entry with specific project. Can be ID or name of the project (ENV: TOGGL_PROJECT)', )
@click.option('--workspace', '-w', envvar="TOGGL_WORKSPACE", type=types.ResourceType(api.Workspace),
              help='Link the entry with specific workspace. Can be ID or name of the workspace (ENV: TOGGL_WORKSPACE)')
@click.pass_context
def entry_now(ctx, **kwargs):
    """
    Manages currently running entry.

    Without any options the command fetches the current time entry and displays it. But it also supports modification
    of the current time entry through the options listed below.
    """
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

    helpers.entity_detail(api.TimeEntry, current, primary_field='description', config=ctx.obj['config'])


@cli.command('stop', short_help='stops current time entry')
@click.option('--stop', '-p', type=types.DateTimeType(allow_now=True), help='Sets stop time.')
@click.pass_context
def entry_stop(ctx, stop):
    """
    Stops the current time entry.
    """
    current = api.TimeEntry.objects.current(config=ctx.obj['config'])

    if current is None:
        click.echo('There is no time entry running!')
        exit(1)

    current.stop_and_save(stop)

    click.echo('\'{}\' was stopped'.format(current.description))


@cli.command('continue', short_help='continue a time entry')
@click.argument('descr', required=False, type=types.ResourceType(api.TimeEntry))
@click.option('--start', '-s', type=types.DateTimeType(), help='Sets a start time.')
@click.pass_context
def entry_continue(ctx, descr, start):
    """
    Takes the last time entry and continue its logging.

    The underhood behaviour of Toggl is that it actually creates a new entry with the same description.
    """
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
    """
    Subcommand for management of Clients
    """
    pass


@clients.command('add', short_help='create new client')
@click.option('--name', '-n', prompt='Name of the client',
              help='Specifies the name of the client', )
@click.option('--notes', help='Specifies a note linked to the client', )
@click.option('--workspace', '-w', envvar="TOGGL_WORKSPACE", type=types.ResourceType(api.Workspace),
              help='Specifies a workspace where the client will be created. Can be ID or name of the workspace '
                   '(ENV: TOGGL_WORKSPACE)')
@click.pass_context
def clients_add(ctx, name, note, workspace):
    """
    Creates a new client.
    """
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
    """
    Updates a client specified by SPEC argument. SPEC can be either ID or Name of the client.
    """
    helpers.entity_update(api.Client, spec, config=ctx.obj['config'], **kwargs)


@clients.command('ls', short_help='list clients')
@click.pass_context
def clients_ls(ctx):
    """
    Lists all clients in the workspace.
    """
    helpers.entity_listing(api.Client, fields=('name', 'id', 'notes'), config=ctx.obj['config'])


@clients.command('get', short_help='retrieve details of a client')
@click.argument('spec')
@click.pass_context
def clients_get(ctx, spec):
    """
    Gets details of a client specified by SPEC argument. SPEC can be either ID or Name of the client.
    """
    helpers.entity_detail(api.Client, spec, config=ctx.obj['config'])


@clients.command('rm', short_help='delete a specific client')
@click.argument('spec')
@click.pass_context
def clients_rm(ctx, spec):
    """
    Removes a client specified by SPEC argument. SPEC can be either ID or Name of the client.
    """
    helpers.entity_remove(api.Client, spec, config=ctx.obj['config'])


# ----------------------------------------------------------------------------
# Projects
# ----------------------------------------------------------------------------
@cli.group('projects', short_help='projects management')
@click.pass_context
def projects(ctx):
    """
    Subcommand for management of projects
    """
    pass


@projects.command('add', short_help='create new project')
@click.option('--name', '-n', prompt='Name of the project',
              help='Specifies the name of the project', )
@click.option('--client', '-c', envvar="TOGGL_CLIENT", type=types.ResourceType(api.Client),
              help='Specifies a client to which the project will be assigned to. Can be ID or name of the client ('
                   'ENV: TOGGL_CLIENT)')
@click.option('--workspace', '-w', envvar="TOGGL_WORKSPACE", type=types.ResourceType(api.Workspace),
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
    """
    Creates a new project.
    """
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
@click.option('--customer', '-c', type=types.ResourceType(api.Client),
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
    """
    Updates a project specified by SPEC which is either ID or Name of the project.
    """
    helpers.entity_update(api.Project, spec, config=ctx.obj['config'], **kwargs)


@projects.command('ls', short_help='list projects')
@click.option('--fields', '-f', type=types.FieldsType(api.Project), default='name,customer,active,id',
              help='Defines a set of fields of which will be displayed. It is also possible to modify default set of fields using \'+\' and/or \'-\' characters. Supported values: ' + types.FieldsType.format_fields_for_help(api.Project))
@click.pass_context
def projects_ls(ctx, fields):
    """
    Lists all projects for the workspace.
    """
    helpers.entity_listing(api.Project, fields, config=ctx.obj['config'])


@projects.command('get', short_help='retrieve details of a project')
@click.argument('spec')
@click.pass_context
def projects_get(ctx, spec):
    """
    Retrieves details of project specified by SPEC which is either ID or Name of the project.
    """
    helpers.entity_detail(api.Project, spec, config=ctx.obj['config'])


@projects.command('rm', short_help='delete a specific client')
@click.argument('spec')
@click.pass_context
def projects_rm(ctx, spec):
    """
    Removes a project specified by SPEC which is either ID or Name of the project.
    """
    helpers.entity_remove(api.Project, spec, config=ctx.obj['config'])


# ----------------------------------------------------------------------------
# Workspaces
# ----------------------------------------------------------------------------
# TODO: Leave workspace
# TODO: Create workspace

@cli.group('workspaces', short_help='workspaces management')
@click.pass_context
def workspaces(ctx):
    """
    Subcommand for management of workspaces.
    """
    pass


@workspaces.command('ls', short_help='list workspaces')
@click.option('--fields', '-f', type=types.FieldsType(api.Workspace), default='name,premium,admin,id',
              help='Defines a set of fields which will be displayed. It is also possible to modify default set of fields using \'+\' and/or \'-\' characters. Supported values: ' + types.FieldsType.format_fields_for_help(api.Workspace))
@click.pass_context
def workspaces_ls(ctx, fields):
    """
    Lists all workspaces available to the current user.
    """
    helpers.entity_listing(api.Workspace, fields, config=ctx.obj['config'])


@workspaces.command('get', short_help='retrieve details of a workspace')
@click.argument('spec')
@click.pass_context
def workspaces_get(ctx, spec):
    """
    Retrieves details of a workspace specified by SPEC which is either ID or Name of the workspace.
    """
    helpers.entity_detail(api.Workspace, spec, config=ctx.obj['config'])


# ----------------------------------------------------------------------------
# Tasks
# ----------------------------------------------------------------------------

@cli.group('tasks', short_help='tasks management')
@click.pass_context
def tasks(ctx):
    """
    Subcommand for management of tasks.

    Tasks is a premium feature of a Toggl, therefore you can use this subcommand only together with payed workspace.
    In case the workspace is not paid, the commands will fail.
    """
    pass


@tasks.command('add', short_help='create new task')
@click.option('--name', '-n', prompt='Name of the task',
              help='Specifies the name of the task', )
@click.option('--estimated_seconds', '-e', type=click.INT, help='Specifies estimated duration for the task in seconds')
@click.option('--active/--no-active', default=True, help='Specifies whether the task is active', )
@click.option('--workspace', '-w', envvar="TOGGL_WORKSPACE", type=types.ResourceType(api.Workspace),
              help='Specifies a workspace where the client will be created. Can be ID or name of the workspace '
                   '(ENV: TOGGL_WORKSPACE)')
@click.option('--project', '-p', prompt='Name or ID of project to have the task assigned to', envvar="TOGGL_PROJECT", type=types.ResourceType(api.Project),
              help='Specifies a project to which the task will be linked to. Can be ID or name of the project '
                   '(ENV: TOGGL_PROJECT)')
@click.option('--user', '-u', envvar="TOGGL_USER", type=types.ResourceType(api.User),
              help='Specifies a user to whom the task will be assigned. Can be ID or name of the user '
                   '(ENV: TOGGL_USER)')
@click.pass_context
def tasks_add(ctx, **kwargs):
    """
    Creates a new task.
    """
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
@click.option('--user', '-u', envvar="TOGGL_USER", type=types.ResourceType(api.User),
              help='Specifies a user to whom the task will be assigned. Can be ID or name of the user '
                   '(ENV: TOGGL_USER)')
@click.pass_context
def tasks_update(ctx, spec, **kwargs):
    """
    Updates a task specified by SPEC which is either ID or Name of the task.
    """
    helpers.entity_update(api.Task, spec, config=ctx.obj['config'], **kwargs)


@tasks.command('ls', short_help='list tasks')
@click.option('--fields', '-f', type=types.FieldsType(api.Task), default='name,project,user,id',
              help='Defines a set of fields which will be displayed. It is also possible to modify default set of fields using \'+\' and/or \'-\' characters. Supported values: ' + types.FieldsType.format_fields_for_help(api.Task))
@click.pass_context
def tasks_ls(ctx, fields):
    """
    Lists tasks for current workspace.
    """
    helpers.entity_listing(api.Task, fields, config=ctx.obj['config'])


@tasks.command('get', short_help='retrieve details of a task')
@click.argument('spec')
@click.pass_context
def tasks_get(ctx, spec):
    """
    Retrieves details of a task specified by SPEC which is either ID or Name of the task.
    """
    helpers.entity_detail(api.Task, spec, config=ctx.obj['config'])


@tasks.command('rm', short_help='delete a specific task')
@click.argument('spec')
@click.pass_context
def tasks_rm(ctx, spec):
    """
    Removes a task specified by SPEC which is either ID or Name of the task.
    """
    helpers.entity_remove(api.Task, spec, config=ctx.obj['config'])


# ----------------------------------------------------------------------------
# Users
# ----------------------------------------------------------------------------
@cli.group('users', short_help='users management')
@click.pass_context
def users(ctx):
    """
    Subcommand for management of users.
    """
    pass


@users.command('ls', short_help='list users')
@click.option('--fields', '-f', type=types.FieldsType(api.User), default='email, fullname, id',
              help='Defines a set of fieldswhich will be displayed. It is also possible to modify default set of fields using \'+\' and/or \'-\' characters. Supported values: ' + types.FieldsType.format_fields_for_help(api.User))
@click.pass_context
def users_ls(ctx, fields):
    """
    List users for current workspace.
    """
    helpers.entity_listing(api.User, fields, config=ctx.obj['config'])


@users.command('get', short_help='retrieve details of a user')
@click.argument('spec')
@click.pass_context
def users_get(ctx, spec):
    """
    Retrieves details of a user specified by SPEC which is either ID, Email or Fullname.
    """
    helpers.entity_detail(api.User, spec, ('id', 'email', 'fullname'), 'email', config=ctx.obj['config'])


@users.command('signup', short_help='sign up a new user')
@click.option('--email', '-e', help='Email address which represents the new user\'s account',
              prompt='Email of the user to sign up')
@click.option('--password', '-p', help='Password for the new user\'s account', hide_input=True,
              confirmation_prompt=True, prompt='Password of a user to sign up')
@click.option('--timezone', '-t', help='Timezone which will be used for all date/time operations')
@click.option('--created-with', '-c', help='Information about which application created the user\' account')
@click.pass_context
def users_signup(ctx, email, password, timezone=None, created_with=None):
    """
    Creates a new user.

    After running the command the user will receive confirmation email.
    """
    user = api.User.signup(email, password, timezone, created_with, config=ctx.obj['config'])

    click.echo("User '{}' was successfully created with ID #{}.".format(email, user.id))


# ----------------------------------------------------------------------------
# Workspace users
# ----------------------------------------------------------------------------
@cli.group('workspace_users', short_help='workspace\'s users management (eq. access management for the workspace)')
@click.pass_context
def workspace_users(ctx):
    """
    Subcommand for management of workspace's users.
    """
    pass


@workspace_users.command('ls', short_help='list workspace\'s users')
@click.option('--fields', '-f', type=types.FieldsType(api.WorkspaceUser), default='email,active,admin',
              help='Defines a set of fields which will be displayed. It is also possible to modify default set of fields using \'+\' and/or \'-\' characters. Supported values: ' + types.FieldsType.format_fields_for_help(api.WorkspaceUser))
@click.pass_context
def workspace_users_ls(ctx, fields):
    """
    Lists all users in current workspace and some related information.
    """
    helpers.entity_listing(api.WorkspaceUser, fields, config=ctx.obj['config'])


@workspace_users.command('get', short_help='retrieve details of a user')
@click.argument('spec')
@click.pass_context
def workspace_users_get(ctx, spec):
    """
    Retrieves detail of a workspace's user specified by SPEC which is either ID or Email.
    """
    helpers.entity_detail(api.WorkspaceUser, spec, ('id', 'email'), 'email', config=ctx.obj['config'])


@workspace_users.command('invite', short_help='invite new user into workspace')
@click.option('--email', '-e', help='Email address where will be the invite to the workspace send',
              prompt='Email of a user to invite to the workspace')
@click.pass_context
def workspace_users_invite(ctx, email):
    """
    Invites a new user into the current workspace. It can be either an existing user or somebody who is not present at the
    Toggl platform. After the invitation is sent, the user needs to accept invitation to be fully part of the workspace.
    """
    api.WorkspaceUser.invite(email, config=ctx.obj['config'])

    click.echo("User '{}' was successfully invited! He needs to accept the invitation now.".format(email))


@workspace_users.command('rm', short_help='delete a specific workspace\'s user')
@click.argument('spec')
@click.pass_context
def workspace_users_rm(ctx, spec):
    """
    Removes a user from the current workspace. User is specified by SPEC which is either ID or Email.
    """
    helpers.entity_remove(api.WorkspaceUser, spec, ('id', 'email'), config=ctx.obj['config'])


@workspace_users.command('update', short_help='update a specific workspace\'s user')
@click.argument('spec')
@click.option('--admin/--no-admin', default=None,
              help='Specifies if the workspace\'s user is admin for the workspace', )
@click.pass_context
def workspace_users_update(ctx, spec, **kwargs):
    """
    Updates a workspace user specified by SPEC which is either ID or Email.
    """
    helpers.entity_update(api.WorkspaceUser, spec, ('id', 'email'), config=ctx.obj['config'], **kwargs)