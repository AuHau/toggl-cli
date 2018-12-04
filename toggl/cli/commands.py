import logging
import traceback
import webbrowser
import os

import click
import click_completion

import pendulum
from prettytable import PrettyTable

from .. import api, exceptions, utils, __version__
from . import helpers, types

DEFAULT_CONFIG_PATH = '~/.togglrc'

logger = logging.getLogger('toggl.cli.commands')
click_completion.init()


# TODO: Improve better User's management. Hide all the Project's users/Workspace's users and work only with User object
# ==> for that support for mapping filter needs to be written (eq. user.email == 'test@test.org')

def entrypoint(args, obj=None):
    """
    CLI entry point, where exceptions are handled.

    If the exceptions should be propagated out of the tool use env. variable: TOGGL_EXCEPTIONS=1
    """

    try:
        cli(args, obj=obj or {})
    except exceptions.TogglException as e:
        logger.error(str(e).strip())
        logger.debug(traceback.format_exc())
        exit(e.exit_code)
    except Exception as e:
        if os.environ.get('TOGGL_EXCEPTIONS') == '1':
            raise

        logger.error(str(e).strip())
        logger.debug(traceback.format_exc())
        exit(1)


@click.group(cls=utils.SubCommandsGroup)
@click.option('--quiet', '-q', is_flag=True, help="Don't print anything")
@click.option('--verbose', '-v', is_flag=True, help="Prints additional info")
@click.option('--debug', '-d', is_flag=True, help="Prints debugging output")
@click.option('--header/--no-header', default=True, help="Specifies if header/labels of data should be displayed")
@click.option('--simple', '-s', is_flag=True,
              help="Instead of pretty aligned tables prints only data separated by tabulator")
@click.option('--config', type=click.Path(), envvar='TOGGL_CONFIG',
              help="Sets specific Config file to be used (ENV: TOGGL_CONFIG)")
@click.version_option(__version__)
@click.pass_context
def cli(ctx, quiet, verbose, debug, simple, header, config=None):
    """
    CLI interface to interact with Toggl tracking application.

    Many of the options can be set through Environmental variables. The names of the variables
    are denoted in the option's helps with format "(ENV: <name of variable>)".

    The authentication credentials can be also overridden with Environmental variables. Use
    TOGGL_API_TOKEN or TOGGL_USERNAME, TOGGL_PASSWORD.

    \b
    Currently known limitations:
     * For every non-ID (using names, emails etc.) resource lookup the lookup is done
       in the default workspace, unless there is option to specify workspace in the command.

    \b
    Known exit codes:
     * 0 - Successful execution
     * 1 - Unknown error
     * 10 - Command failed because of API throttling
     * 40 - The passed data are not valid
     * 42 - Tries to use Premium features on Non-premium workspace
     * 43 - Authentication failed
     * 44 - Resource defined by SPEC not found
    """
    if ctx.obj.get('config') is None:
        if config is None:
            config = utils.Config.factory()
        else:
            config = utils.Config.factory(config)

        if not config.is_loaded:
            config.cli_bootstrap()
            config.persist()

        ctx.obj['config'] = config
    else:
        config = ctx.obj['config']

    main_logger = logging.getLogger('toggl')
    main_logger.setLevel(logging.DEBUG)

    # Logging to Stderr
    default = logging.StreamHandler()
    default_formatter = logging.Formatter('%(levelname)s: %(message)s')
    default.setFormatter(default_formatter)

    ctx.obj['simple'] = simple
    ctx.obj['header'] = header

    if verbose:
        default.setLevel(logging.INFO)
    elif debug:
        default.setLevel(logging.DEBUG)
    else:
        default.setLevel(logging.ERROR)

    if quiet:
        # TODO: [Q/Design] Is this good idea?
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
@click.argument('stop', type=types.DateTimeDurationType())
@click.argument('descr')
@click.option('--tags', '-a', type=types.SetType(), help='List of tags delimited with \',\'')
@click.option('--project', '-o', envvar="TOGGL_PROJECT", type=types.ResourceType(api.Project),
              help='Link the entry with specific project. Can be ID or name of the project (ENV: TOGGL_PROJECT)', )
@click.option('--task', '-t', envvar="TOGGL_TASK", type=types.ResourceType(api.Task),
              help='Link the entry with specific task. Can be ID or name of the task (ENV: TOGGL_TASK)', )
@click.option('--workspace', '-w', envvar="TOGGL_WORKSPACE", type=types.ResourceType(api.Workspace),
              help='Link the entry with specific workspace. Can be ID or name of the workspace (ENV: TOGGL_WORKSPACE)')
@click.pass_context
def entry_add(ctx, start, stop, descr, **kwargs):
    """
    Adds finished time entry to Toggl with DESCR description and start
    datetime START which can also be a special string 'now' that denotes current
    datetime. The entry also has STOP argument which is either specific
    datetime or duration.

    \b
    Duration syntax:
     - 'd' : days
     - 'h' : hours
     - 'm' : minutes
     - 's' : seconds

    Example: 5h2m10s - 5 hours 2 minutes 10 seconds from the start time
    """
    if isinstance(stop, pendulum.Duration):
        stop = start + stop

    # Create a time entry.
    entry = api.TimeEntry(
        config=ctx.obj['config'],
        description=descr,
        start=start,
        stop=stop,
        **kwargs
    )

    entry.save()
    click.echo("Time entry '{}' with #{} created.".format(entry.description, entry.id))


# TODO: [Feature/Medium] Make possible to list really all time-entries, not first 1000 in last 9 days
@cli.command('ls', short_help='list a time entries')
@click.option('--start', '-s', type=types.DateTimeType(),
              help='Defines start of a date range to filter the entries by.')
@click.option('--stop', '-p', type=types.DateTimeType(), help='Defines stop of a date range to filter the entries by.')
@click.option('--project', '-o', type=types.ResourceType(api.Project),
              help='Filters the entries by project. Can be ID or name of the project.', )
@click.option('--tags', '-a', type=types.SetType(), help='Filters the entries by list of tags delimited with \',\'')
@click.option('--fields', '-f', type=types.FieldsType(api.TimeEntry), default='description,duration,start,stop',
              help='Defines a set of fields of time entries, which will be displayed. It is also possible to modify '
                   'default set of fields using \'+\' and/or \'-\' characters. Supported values: '
                   + types.FieldsType.format_fields_for_help(api.TimeEntry))
@click.pass_context
def entry_ls(ctx, fields, **conditions):
    """
    Lists time entries the user has access to.

    The list is limited with 1000 entries in last 9 days. The list visible
    through this utility and on toggl's web client might differ in the range
    as they developing new version of API and they are able to see in the future
    and also longer into past.
    """

    conditions = {key: condition for key, condition in conditions.items() if condition is not None}
    if conditions:
        entities = api.TimeEntry.objects.filter(order='desc', config=ctx.obj['config'], **conditions)
    else:
        entities = api.TimeEntry.objects.all(order='desc', config=ctx.obj['config'])

    if not entities:
        click.echo('No entries were found!')
        exit(0)

    entities = sorted(entities, key=lambda x: x.start, reverse=True)

    if ctx.obj.get('simple'):
        if ctx.obj.get('header'):
            click.echo('\t'.join([click.style(field.capitalize(), fg='white', dim=1) for field in fields]))

        for entity in entities:
            click.echo('\t'.join(
                [str(entity.__fields__[field].format(getattr(entity, field, ''))) for field in fields]
            ))
        return

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
                value = str(entity.__fields__[field].format(getattr(entity, field, ''), instance=entity,
                                                            display_running=True))
            elif field == 'start':
                value = str(entity.__fields__[field].format(getattr(entity, field, ''), instance=entity,
                                                            only_time_for_same_day=entity.stop))
            else:
                value = str(entity.__fields__[field].format(getattr(entity, field, '')))
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
    helpers.entity_remove(api.TimeEntry, spec, ('id', 'description'), obj=ctx.obj)


@cli.command('start', short_help='starts new time entry')
@click.argument('descr', required=False)
@click.option('--start', '-s', type=types.DateTimeType(allow_now=True), help='Specifies start of the time entry. '
                                                                             'If left empty \'now\' is assumed.')
@click.option('--tags', '-a', type=types.SetType(), help='List of tags delimited with \',\'')
@click.option('--project', '-o', envvar="TOGGL_PROJECT", type=types.ResourceType(api.Project),
              help='Link the entry with specific project. Can be ID or name of the project (ENV: TOGGL_PROJECT)', )
@click.option('--workspace', '-w', envvar="TOGGL_WORKSPACE", type=types.ResourceType(api.Workspace),
              help='Link the entry with specific workspace. Can be ID or name of the workspace (ENV: TOGGL_WORKSPACE)')
@click.pass_context
def entry_start(ctx, descr, **kwargs):
    """
    Starts a new time entry with description DESCR (it can be left out). If there is another currently running entry,
    the entry will be stopped and new entry started.
    """
    api.TimeEntry.start_and_save(
        config=ctx.obj['config'],
        description=descr,
        **kwargs
    )


@cli.command('now', short_help='manage current time entry')
@click.option('--description', '-d', help='Sets description')
@click.option('--start', '-s', type=types.DateTimeType(allow_now=True), help='Sets starts time.')
@click.option('--tags', '-a', type=types.ModifierSetType(), help='Modifies the tags. List of values delimited by \',\'.'
                                                                 'Support either modification or specification mode. '
                                                                 'More info above.')
@click.option('--project', '-o', type=types.ResourceType(api.Project),
              help='Link the entry with specific project. Can be ID or name of the project', )
@click.option('--workspace', '-w', type=types.ResourceType(api.Workspace),
              help='Link the entry with specific workspace. Can be ID or name of the workspace')
@click.pass_context
def entry_now(ctx, tags, **kwargs):
    """
    Manages currently running entry.

    Without any options the command fetches the current time entry and displays it. But it also supports modification
    of the current time entry through the options listed below.

    Tags can be modified either in a way of specifing new set of tags delimited with ',' character,
    or add/remove tags using +/- characters. Examples: 'a,b,c,d' will remove all previous tags and add a,b,c,d tags.
    '+z,-a' will remove tag 'a' and add tag 'z' to the already existing tag list.
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

    if tags is not None:
        if isinstance(tags, types.Modifier):
            current.tags = current.tags - tags.remove_set | tags.add_set
        else:
            current.tags = tags

        updated = True

    if updated:
        current.save()

    helpers.entity_detail(api.TimeEntry, current, primary_field='description', obj=ctx.obj)


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

    click.echo('\'{}\' was stopped'.format(getattr(current, 'description', '<Entry without description>')))


@cli.command('continue', short_help='continue a time entry')
@click.argument('descr', required=False, type=types.ResourceType(api.TimeEntry))
@click.option('--start', '-s', type=types.DateTimeType(), help='Sets a start time.')
@click.pass_context
def entry_continue(ctx, descr, start):
    """
    If DESCR is specified then it will search this entry and continue it, otherwise it continues the last time entry.

    The underhood behaviour of Toggl is that it actually creates a new entry with the same description.
    """
    entry = None
    try:
        if descr is None:
            entry = api.TimeEntry.objects.all(order='desc', config=ctx.obj['config'])[0]
        else:
            entry = api.TimeEntry.objects.filter(contain=True, description=descr, config=ctx.obj['config'])[0]
    except IndexError:
        click.echo('You don\'t have any time entries in past 9 days!')
        exit(1)

    entry.continue_and_save(start=start)

    click.echo('Time entry \'{}\' continue!'.format(getattr(entry, 'description', '<Entry without description>')))


# ----------------------------------------------------------------------------
# Clients
# ----------------------------------------------------------------------------

@cli.group('clients', short_help='clients management')
@click.option('--workspace', '-w', envvar="TOGGL_WORKSPACE", type=types.ResourceType(api.Workspace),
              help='Specifies a workspace in which the clients will be managed in. Can be ID or name of the workspace '
                   '(ENV: TOGGL_WORKSPACE)')
@click.pass_context
def clients(ctx, workspace):
    """
    Subcommand for management of Clients
    """
    ctx.obj['workspace'] = workspace


@clients.command('add', short_help='create new client')
@click.option('--name', '-n', prompt='Name of the client',
              help='Specifies the name of the client', )
@click.option('--notes', help='Specifies a note linked to the client', )
@click.pass_context
def clients_add(ctx, **kwargs):
    """
    Creates a new client.
    """
    client = api.Client(
        workspace=ctx.obj['workspace'],
        config=ctx.obj['config'],
        **kwargs
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

    If SPEC is Name, then the lookup is done in the default workspace, unless --workspace is specified.
    """
    helpers.entity_update(api.Client, spec, obj=ctx.obj, **kwargs)


@clients.command('ls', short_help='list clients')
@click.pass_context
def clients_ls(ctx):
    """
    Lists all clients in the workspace.
    """
    helpers.entity_listing(api.Client, fields=('name', 'id', 'notes'), obj=ctx.obj)


@clients.command('get', short_help='retrieve details of a client')
@click.argument('spec')
@click.pass_context
def clients_get(ctx, spec):
    """
    Gets details of a client specified by SPEC argument. SPEC can be either ID or Name of the client.

    If SPEC is Name, then the lookup is done in the default workspace, unless --workspace is specified.
    """
    helpers.entity_detail(api.Client, spec, obj=ctx.obj)


@clients.command('rm', short_help='delete a client')
@click.confirmation_option(prompt='Are you sure you want to remove the client?')
@click.argument('spec')
@click.pass_context
def clients_rm(ctx, spec):
    """
    Removes a client specified by SPEC argument. SPEC can be either ID or Name of the client.

    If SPEC is Name, then the lookup is done in the default workspace, unless --workspace is specified.
    """
    helpers.entity_remove(api.Client, spec, obj=ctx.obj)


# ----------------------------------------------------------------------------
# Projects
# ----------------------------------------------------------------------------
@cli.group('projects', short_help='projects management')
@click.option('--workspace', '-w', envvar="TOGGL_WORKSPACE", type=types.ResourceType(api.Workspace),
              help='Specifies a workspace in which the projects will be managed in. Can be ID or name of the workspace '
                   '(ENV: TOGGL_WORKSPACE)')
@click.pass_context
def projects(ctx, workspace):
    """
    Subcommand for management of projects
    """
    ctx.obj['workspace'] = workspace


@projects.command('add', short_help='create new project')
@click.option('--name', '-n', prompt='Name of the project',
              help='Specifies the name of the project', )
@click.option('--client', '-c', envvar="TOGGL_CLIENT", type=types.ResourceType(api.Client),
              help='Specifies a client to which the project will be assigned to. Can be ID or name of the client ('
                   'ENV: TOGGL_CLIENT)')
@click.option('--private', '-p', is_flag=True, help='Specifies whether project is accessible for all workspace users ('
                                                    '=public) or just only project\'s users (=private). '
                                                    'By default it is public.')
@click.option('--billable', '-b', is_flag=True, default=False, help='Specifies whether project is billable or not. '
                                                                    '(Premium only)')
@click.option('--auto-estimates', is_flag=True, default=False,
              help='Specifies whether the estimated hours should be automatically calculated based on task estimations '
                   '(Premium only)')
@click.option('--rate', '-r', type=click.FLOAT, help='Hourly rate of the project (Premium only)')
@click.option('--color', type=click.INT, help='ID of color used for the project')
@click.pass_context
def projects_add(ctx, public=None, **kwargs):
    """
    Creates a new project.
    """
    project = api.Project(
        is_private=not public,
        workspace=ctx.obj['workspace'],
        config=ctx.obj['config'],
        **kwargs
    )

    project.save()
    click.echo("Project '{}' with #{} created.".format(project.name, project.id))


@projects.command('update', short_help='update a project')
@click.argument('spec')
@click.option('--name', '-n', help='Specifies the name of the project', )
@click.option('--client', '-c', type=types.ResourceType(api.Client),
              help='Specifies a client to which the project will be assigned to. Can be ID or name of the client')
@click.option('--private/--public', 'is_private', default=None,
              help='Specifies whether project is accessible for all workspace'
                   ' users (=public) or just only project\'s users.')
@click.option('--billable/--no-billable', default=None, help='Specifies whether project is billable or not.'
                                                             ' (Premium only)')
@click.option('--auto-estimates/--no-auto-estimates', default=None,
              help='Specifies whether the estimated hours are automatically calculated based on task estimations or'
                   ' manually fixed based on the value of \'estimated_hours\' (Premium only)')
@click.option('--rate', '-r', type=click.FLOAT, help='Hourly rate of the project (Premium only)')
@click.option('--color', type=click.INT, help='ID of color used for the project')
@click.pass_context
def projects_update(ctx, spec, **kwargs):
    """
    Updates a project specified by SPEC which is either ID or Name of the project.
    """
    helpers.entity_update(api.Project, spec, obj=ctx.obj, **kwargs)


@projects.command('ls', short_help='list projects')
@click.option('--fields', '-f', type=types.FieldsType(api.Project), default='name,client,active,id',
              help='Defines a set of fields of which will be displayed. It is also possible to modify default set of'
                   ' fields using \'+\' and/or \'-\' characters. Supported values: '
                   + types.FieldsType.format_fields_for_help(api.Project))
@click.pass_context
def projects_ls(ctx, fields):
    """
    Lists all projects for the workspace.
    """
    helpers.entity_listing(api.Project, fields, obj=ctx.obj)


@projects.command('get', short_help='retrieve details of a project')
@click.argument('spec')
@click.pass_context
def projects_get(ctx, spec):
    """
    Retrieves details of project specified by SPEC which is either ID or Name of the project.
    """
    helpers.entity_detail(api.Project, spec, obj=ctx.obj)


@projects.command('rm', short_help='delete a project')
@click.confirmation_option(prompt='Are you sure you want to remove the project?')
@click.argument('spec')
@click.pass_context
def projects_rm(ctx, spec):
    """
    Removes a project specified by SPEC which is either ID or Name of the project.
    """
    helpers.entity_remove(api.Project, spec, obj=ctx.obj)


@projects.group('users', short_help='user management for projects')
@click.argument('project', type=types.ResourceType(api.Project))
@click.pass_context
def project_users(ctx, project):
    """
    Manages assigned users to a specific project specified by PROJECT, which can be either ID or Name of the project.
    """
    ctx.obj['project'] = project


@project_users.command('ls', short_help='list project\'s users')
@click.option('--fields', '-f', type=types.FieldsType(api.ProjectUser), default='user,manager,rate,id',
              help='Defines a set of fields of which will be displayed. It is also possible to modify default set of '
                   'fields using \'+\' and/or \'-\' characters. Supported values: '
                   + types.FieldsType.format_fields_for_help(api.ProjectUser))
@click.pass_context
def project_users_ls(ctx, fields):
    """
    Lists all project's users.
    """
    project = ctx.obj['project']
    src = api.ProjectUser.objects.filter(project=project, config=ctx.obj['config'])

    helpers.entity_listing(src, fields)


@project_users.command('add', short_help='add a user into the project')
@click.option('--user', '-u', prompt='Enter ID or Email of the user to add to project',
              help='User to be added. Can be ID or email of the user',
              type=types.ResourceType(api.User, fields=('id', 'email')))
@click.option('--rate', '-f', default=None, type=click.FLOAT, help='Hourly rate for the project user')
@click.option('--manager/--no-manager', default=False, help='Admin rights for the project', )
@click.pass_context
def project_users_add(ctx, user, **kwargs):
    """
    Adds new user to the project.
    """
    client = api.ProjectUser(
        project=ctx.obj['project'],
        config=ctx.obj['config'],
        user=user,
        **kwargs
    )

    client.save()
    click.echo("User '{}' added to the project.".format(user.email))


@project_users.command('update', short_help='update a project\'s user')
@click.argument('spec')
@click.option('--rate', '-f', type=click.FLOAT, default=None, help='Hourly rate for the project user')
@click.option('--manager/--no-manager', default=None, help='Admin rights for the project', )
@click.pass_context
def project_users_update(ctx, spec, **kwargs):
    """
    Updates project's user specified by SPEC, which can be only ID of the project's user (not user itself).
    """
    helpers.entity_update(api.ProjectUser, spec, field_lookup=('id',), obj=ctx.obj, **kwargs)


@project_users.command('rm', short_help='remove a project\'s user')
@click.argument('spec')
@click.pass_context
def project_users_remove(ctx, spec):
    """
    Removes project's user specified by SPEC, which can be only ID of the project's user (not user itself).
    """
    helpers.entity_remove(api.ProjectUser, spec, field_lookup=('id',), obj=ctx.obj)


# ----------------------------------------------------------------------------
# Workspaces
# ----------------------------------------------------------------------------
# TODO: Leave workspace: DELETE to /v8/workspaces/XXX/leave
# TODO: Create workspace

@cli.group('workspaces', short_help='workspaces management')
@click.pass_context
def workspaces(_):
    """
    Subcommand for management of workspaces.
    """
    pass


@workspaces.command('ls', short_help='list workspaces')
@click.option('--fields', '-f', type=types.FieldsType(api.Workspace), default='name,premium,admin,id',
              help='Defines a set of fields which will be displayed. It is also possible to modify default set of '
                   'fields using \'+\' and/or \'-\' characters. Supported values: '
                   + types.FieldsType.format_fields_for_help(api.Workspace))
@click.pass_context
def workspaces_ls(ctx, fields):
    """
    Lists all workspaces available to the current user.
    """
    helpers.entity_listing(api.Workspace, fields, obj=ctx.obj)


@workspaces.command('get', short_help='retrieve details of a workspace')
@click.argument('spec', required=False)
@click.pass_context
def workspaces_get(ctx, spec):
    """
    Retrieves details of a workspace specified by SPEC which is either ID or Name of the workspace.

    You can leave SPEC empty, which will then retrieve your default workspace.
    """
    config = ctx.obj['config']
    if spec is None:
        spec = config.default_workspace

    helpers.entity_detail(api.Workspace, spec, obj=ctx.obj)


@workspaces.group('users', short_help='user management for workspace')
@click.option('--workspace', '-w', envvar="TOGGL_WORKSPACE", type=types.ResourceType(api.Workspace),
              help='Specifies a workspace in which the workspace users will be managed in. '
                   'Can be ID or name of the workspace (ENV: TOGGL_WORKSPACE)')
@click.pass_context
def workspace_users(ctx, workspace):
    """
    Manages assigned users to a specific workspace specified by --workspace option, if not specified the default
    workspace is used.
    """
    ctx.obj['workspace'] = workspace or ctx.obj['config'].default_workspace


@workspace_users.command('invite', short_help='invite an user into workspace')
@click.option('--email', '-e', help='Email address of the user to invite into the workspace',
              prompt='Email address of the user to invite into the workspace')
@click.pass_context
def workspace_users_invite(ctx, email):
    """
    Invites an user into the workspace.

    It can be either an existing user or somebody who is not present at the Toggl platform.
    After the invitation is sent, the user needs to accept invitation to be fully part of the workspace.
    """
    workspace = ctx.obj['workspace']
    workspace.invite(email)

    click.echo("User '{}' was successfully invited! He needs to accept the invitation now.".format(email))


@workspace_users.command('ls', short_help='list workspace\'s users')
@click.option('--fields', '-f', type=types.FieldsType(api.WorkspaceUser), default='email,active,admin,id',
              help='Defines a set of fields which will be displayed. It is also possible to modify default set of '
                   'fields using \'+\' and/or \'-\' characters. Supported values: '
                   + types.FieldsType.format_fields_for_help(api.WorkspaceUser))
@click.pass_context
def workspace_users_ls(ctx, fields):
    """
    Lists all users in current workspace and some related information.

    ID of entries are ID of Workspace User and not User entity!
    """
    workspace = ctx.obj['workspace']
    src = api.WorkspaceUser.objects.filter(workspace=workspace, config=ctx.obj['config'])

    helpers.entity_listing(src, fields, obj=ctx.obj)


@workspace_users.command('rm', short_help='remove an user from workspace')
@click.confirmation_option(prompt='Are you sure you want to remove the user from workspace?')
@click.argument('spec')
@click.pass_context
def workspace_users_rm(ctx, spec):
    """
    Removes a user from the current workspace. User is specified by SPEC which is either Workspace User's ID or Email.
    """
    helpers.entity_remove(api.WorkspaceUser, spec, ('id', 'email'), obj=ctx.obj)


@workspace_users.command('update', short_help='update user\'s setting for the workspace')
@click.argument('spec')
@click.option('--admin/--no-admin', default=None,
              help='Specifies if the user is admin for the workspace', )
@click.pass_context
def workspace_users_update(ctx, spec, **kwargs):
    """
    Updates a workspace user specified by SPEC which is either Workspace User's ID or Email.
    """
    helpers.entity_update(api.WorkspaceUser, spec, ('id', 'email'), obj=ctx.obj, **kwargs)


# ----------------------------------------------------------------------------
# Tasks
# ----------------------------------------------------------------------------

@cli.group('tasks', short_help='tasks management')
@click.option('--workspace', '-w', envvar="TOGGL_WORKSPACE", type=types.ResourceType(api.Workspace),
              help='Specifies a workspace in which the tasks will be managed in. Can be ID or name of the workspace '
                   '(ENV: TOGGL_WORKSPACE)')
@click.pass_context
def tasks(ctx, workspace):
    """
    Subcommand for management of tasks.

    Tasks is a premium feature of a Toggl, therefore you can use this subcommand only together with payed workspace.
    In case the workspace is not paid, the commands will fail.
    """
    ctx.obj['workspace'] = workspace


@tasks.command('add', short_help='create new task')
@click.option('--name', '-n', prompt='Name of the task',
              help='Specifies the name of the task', )
@click.option('--estimated_seconds', '-e', type=click.INT, help='Specifies estimated duration for the task in seconds')
@click.option('--active/--no-active', default=True, help='Specifies whether the task is active', )
@click.option('--project', '-o', prompt='Name or ID of project to have the task assigned to', envvar="TOGGL_PROJECT",
              type=types.ResourceType(api.Project),
              help='Specifies a project to which the task will be linked to. Can be ID or name of the project '
                   '(ENV: TOGGL_PROJECT)')
@click.option('--user', '-u', envvar="TOGGL_USER", type=types.ResourceType(api.User, fields=('id', 'email')),
              help='Specifies a user to whom the task will be assigned. Can be ID or email of the user '
                   '(ENV: TOGGL_USER)')
@click.pass_context
def tasks_add(ctx, **kwargs):
    """
    Creates a new task.
    """
    task = api.Task(config=ctx.obj['config'], workspace=ctx.obj['workspace'], **kwargs)

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
@click.option('--active/--no-active', default=None, help='Specifies whether the task is active', )
@click.option('--user', '-u', type=types.ResourceType(api.User, fields=('id', 'email')),
              help='Specifies a user to whom the task will be assigned. Can be ID or email of the user')
@click.pass_context
def tasks_update(ctx, spec, **kwargs):
    """
    Updates a task specified by SPEC which is either ID or Name of the task.
    """
    helpers.entity_update(api.Task, spec, obj=ctx.obj, **kwargs)


@tasks.command('ls', short_help='list tasks')
@click.option('--fields', '-f', type=types.FieldsType(api.Task), default='name,project,user,id',
              help='Defines a set of fields which will be displayed. It is also possible to modify default set of '
                   'fields using \'+\' and/or \'-\' characters. Supported values: '
                   + types.FieldsType.format_fields_for_help(api.Task))
@click.pass_context
def tasks_ls(ctx, fields):
    """
    Lists tasks for current workspace.
    """
    helpers.entity_listing(api.Task, fields, obj=ctx.obj)


@tasks.command('get', short_help='retrieve details of a task')
@click.argument('spec')
@click.pass_context
def tasks_get(ctx, spec):
    """
    Retrieves details of a task specified by SPEC which is either ID or Name of the task.
    """
    helpers.entity_detail(api.Task, spec, obj=ctx.obj)


@tasks.command('rm', short_help='delete a task')
@click.confirmation_option(prompt='Are you sure you want to remove the task?')
@click.argument('spec')
@click.pass_context
def tasks_rm(ctx, spec):
    """
    Removes a task specified by SPEC which is either ID or Name of the task.
    """
    helpers.entity_remove(api.Task, spec, obj=ctx.obj)


# ----------------------------------------------------------------------------
# Users
# ----------------------------------------------------------------------------
@cli.group('users', short_help='users management')
@click.option('--workspace', '-w', envvar="TOGGL_WORKSPACE", type=types.ResourceType(api.Workspace),
              help='Specifies a workspace in which the users will be managed in. Can be ID or name of the workspace '
                   '(ENV: TOGGL_WORKSPACE)')
@click.pass_context
def users(ctx, workspace):
    """
    Subcommand for management of users.
    """
    ctx.obj['workspace'] = workspace


@users.command('ls', short_help='list users')
@click.option('--fields', '-f', type=types.FieldsType(api.User), default='email, fullname, id',
              help='Defines a set of fields which will be displayed. It is also possible to modify default set of '
                   'fields using \'+\' and/or \'-\' characters. Supported values: '
                   + types.FieldsType.format_fields_for_help(api.User))
@click.pass_context
def users_ls(ctx, fields):
    """
    List users for current workspace.
    """
    helpers.entity_listing(api.User, fields, obj=ctx.obj)


@users.command('get', short_help='retrieve details of a user')
@click.argument('spec')
@click.pass_context
def users_get(ctx, spec):
    """
    Retrieves details of a user specified by SPEC which is either ID, Email or Fullname.
    """
    helpers.entity_detail(api.User, spec, ('id', 'email', 'fullname'), 'email', obj=ctx.obj)


@users.command('signup', short_help='sign up a new user')
@click.option('--email', '-e', help='Email address which represents the new user\'s account',
              prompt='Email of the user to sign up')
@click.option('--password', '-p', help='Password for the new user\'s account', hide_input=True,
              confirmation_prompt=True, prompt='Password of a user to sign up')
@click.option('--timezone', '-t', 'tz', help='Timezone which will be used for all date/time operations')
@click.option('--created-with', '-c', help='Information about which application created the user\' account')
@click.pass_context
def users_signup(ctx, email, password, tz=None, created_with=None):
    """
    Creates a new user.

    After running the command the user will receive confirmation email.
    """
    user = api.User.signup(email, password, tz, created_with, config=ctx.obj['config'])

    click.echo("User '{}' was successfully created with ID #{}.".format(email, user.id))


# ----------------------------------------------------------------------------
# Project users
# ----------------------------------------------------------------------------
@cli.command('project_users', short_help='list all project users in workspace')
@click.option('--fields', '-f', type=types.FieldsType(api.ProjectUser), default='user,project,manager,id',
              help='Defines a set of fields which will be displayed. It is also possible to modify default set of '
                   'fields using \'+\' and/or \'-\' characters. Supported values: '
                   + types.FieldsType.format_fields_for_help(api.ProjectUser))
@click.option('--workspace', '-w', envvar="TOGGL_WORKSPACE", type=types.ResourceType(api.Workspace),
              help='Specifies a workspace in which the project\'s users will be managed in. '
                   'Can be ID or Name of the workspace (ENV: TOGGL_WORKSPACE)')
@click.pass_context
def project_users_listing(ctx, fields, workspace):
    """
    List all project's users inside workspace
    """
    ctx.obj['workspace'] = workspace
    helpers.entity_listing(api.ProjectUser, fields, obj=ctx.obj)


# ----------------------------------------------------------------------------
# Configuration manipulation
# ----------------------------------------------------------------------------
@cli.group('config', short_help='management of configuration')
def user_config():
    """
    Subcommand for managing your configuration.
    """
    pass


@user_config.command('workspace', short_help='retrieves/sets default workspace')
@click.argument('spec', required=False)
@click.option('-t', '--toggl-default', 'default', is_flag=True,
              help='Sets your default workspace to match the Toggl\'s setting. SPEC is ignored.', )
@click.pass_context
def default_workspace(ctx, spec, default):
    """
    Updates your default workspace to one defined by SPEC, which can be either ID or Name of the workspace.
    If you want to set the default workspace to match your Toggl's setting use --toggl-default flag.

    If SPEC is left empty, it prints the current default workspace.
    """
    config = ctx.obj['config']

    if default is True:
        config.default_workspace = None
        config.persist()
        click.echo('Successfully restored the default workspace to Toggl\'s setting')
        exit()

    if spec:
        workspace = helpers.get_entity(api.Workspace, spec, ('id', 'name'), config=config)

        if workspace is None:
            click.echo('Workspace not found!', color='red')
            exit(1)

        config.default_workspace = workspace
        config.persist()
        click.echo('Default workspace successfully set to \'{}\''.format(workspace.name))
        exit()

    if not hasattr(config, 'default_wid'):
        click.echo('Current default workspace: ==Toggl\'s default setting==')
    else:
        click.echo('Current default workspace: {}'.format(config.default_workspace.name))


@user_config.command('timezone', short_help='retrieves/sets timezone')
@click.argument('tz', required=False)
@click.option('-d', '--toggl-default', 'default', is_flag=True,
              help='Sets your timezone to match the Toggl\'s setting. TZ is ignored.', )
@click.pass_context
def timezone(ctx, tz, default):
    """
    Updates your timezone to one defined by TZ.

    If you want to set the timezone to match your Toggl's setting use --toggl-default flag.
    To use your system's timezone set TZ with value 'local'

    If TZ is left empty, it prints the current timezone.
    """
    config = ctx.obj['config']

    if default is True:
        config.timezone = None
        config.persist()
        click.echo('Successfully restored the timezone to Toggl\'s setting')
        exit()

    if tz:
        if tz not in pendulum.timezones and tz != 'local':
            click.echo('Invalid timezone!', color='red')
            exit(1)

        config.timezone = tz
        config.persist()
        click.echo('Timezone successfully set to \'{}\''.format(tz))
        exit()

    if not hasattr(config, 'tz'):
        click.echo('Current timezone: ==Toggl\'s default setting==')
    else:
        click.echo('Current timezone: {}'.format(config.timezone))


cmd_help = """Shell completion for toggl command

Available shell types:

\b
  {}

Default type: auto
""".format("\n  ".join('{:<12} {}'.format(k, click_completion.core.shells[k]) for k in sorted(
    click_completion.core.shells.keys())))


@user_config.group(help=cmd_help, short_help='shell completion for toggl')
def completion():
    pass


@completion.command()
@click.option('-i', '--case-insensitive/--no-case-insensitive', help="Case insensitive completion")
@click.argument('shell', required=False, type=click_completion.DocumentedChoice(click_completion.core.shells))
def show(shell, case_insensitive):
    """Show the toggl completion code"""
    extra_env = {'_TOGGL_CASE_INSENSITIVE_COMPLETE': 'ON'} if case_insensitive else {}
    click.echo(click_completion.core.get_code(shell, extra_env=extra_env))


@completion.command()
@click.option('--append/--overwrite', help="Append the completion code to the file", default=None)
@click.option('-i', '--case-insensitive/--no-case-insensitive', help="Case insensitive completion")
@click.argument('shell', required=False, type=click_completion.DocumentedChoice(click_completion.core.shells))
@click.argument('path', required=False)
def install(append, case_insensitive, shell, path):
    """Install the toggl completion"""
    extra_env = {'_TOGGL_CASE_INSENSITIVE_COMPLETE': 'ON'} if case_insensitive else {}
    shell, path = click_completion.core.install(shell=shell, path=path, append=append, extra_env=extra_env)
    click.echo('%s completion installed in %s' % (shell, path))


