import datetime
import optparse
import os
import re
import sys
import click

from toggl.exceptions import TogglCliException
from . import api, utils, __version__

DEFAULT_CONFIG_PATH = '~/.togglrc'


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
        if value == self.NOW_STRING and self._allow_now:
            return utils.DateAndTime().now()

        try:
            config = ctx.obj.get('config')
            day_first = config.getboolean('options', 'day_first')
            year_first = config.getboolean('options', 'year_first')

            try:
                return utils.DateAndTime().parse_local_datetime_str(value, day_first, year_first)
            except ValueError:
                self.fail("Unknown datetime format!", param, ctx)
        except AttributeError:
            try:
                return utils.DateAndTime().parse_local_datetime_str(value)
            except ValueError:
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
    Takes an Resource class and based on the type of value it calls either
    find_by_id() for integer value or find_by_name() for string value and return
    the appropriate entry.
    """

    def __init__(self, resource, resource_name=None):
        self._resource = resource
        self._resource_name = resource_name

    def convert(self, value, param, ctx):
        try:
            try:
                resource_id = int(value)
                return self._convert_id(resource_id, param, ctx)
            except ValueError:
                pass

            return self._convert_name(value, param, ctx)

        except AttributeError:
            raise TogglCliException("The passed resource class {} does not have expected interface! "
                                    "(find_by_id and find_by_name)".format(self._resource))

    def _convert_id(self, resource_id, param, ctx):
        resource = self._resource().find_by_id(resource_id)

        if resource is None:
            self.fail("Unknown {}'s ID!".format(self._resource_name), param, ctx)

        return resource

    def _convert_name(self, value, param, ctx):
        resource = self._resource().find_by_name(value)

        if resource is None:
            self.fail("Unknown {}'s name!".format(self._resource_name), param, ctx)

        return resource


# ----------------------------------------------------------------------------
# NEW CLI
# ----------------------------------------------------------------------------
@click.group()
@click.option('--quiet', '-q', is_flag=True, help="don't print anything")
@click.option('--verbose', '-v', is_flag=True, help="print additional info")
@click.option('--debug', '-d', is_flag=True, help="print debugging output")
@click.option('--config', type=click.Path(exists=True), envvar='TOGGL_CONFIG',
              help="sets specific Config file to be used (ENV: TOGGL_CONFIG)")
@click.version_option(__version__)
@click.pass_context
def cli(ctx, quiet, verbose, debug, config):
    """
    CLI interface to interact with Toggl tracking application.

    This application implements limited subsets of Toggl's functionality.

    Many of the options can be set through Environmental variables. The names of the variables
    are denoted in the option's helps with format "(ENV: <name of variable>)".

    The authentication credentials can be also overridden with Environmental variables. Use
    TOGGL_API_TOKEN or TOGGL_USERNAME, TOGGL_PASSWORD.
    """
    ctx.obj['config'] = utils.Config.factory()

    # Process command-line options.
    utils.Logger.level = utils.Logger.INFO
    if quiet:
        utils.Logger.level = utils.Logger.NONE
        click.echo = lambda *args: None  # Override echo function to be quiet
    if debug:
        utils.Logger.level = utils.Logger.DEBUG
    if verbose:
        global VERBOSE
        VERBOSE = True


@cli.command('add', short_help='adds finished time entry')
@click.argument('start', type=DateTimeType(allow_now=True))
@click.argument('end', type=DurationType())
@click.argument('descr')
@click.option('--project', '-p', envvar="TOGGL_PROJECT", type=ResourceType(api.ProjectList, 'project'),
              help='Link the entry with specific project. Can be ID or name of the project (ENV: TOGGL_PROJECT)', )
@click.option('--workspace', '-w', envvar="TOGGL_WORKSPACE", type=ResourceType(api.WorkspaceList, 'workspace'),
              help='Link the entry with specific workspace. Can be ID or name of the workspace (ENV: TOGGL_WORKSPACE)')
@click.pass_context
def add_time_entry(ctx, start, end, descr, project, workspace):
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
        start_time=start,
        stop_time=end,
        duration=(end - start).total_seconds(),
        project_name=project['name'] if project else None,
        workspace_name=workspace['name'] if workspace else None
    )

    utils.Logger.debug(entry.json())
    entry.add()
    utils.Logger.info('{} added'.format(descr))


@cli.group('clients', short_help='clients management (default: listing)', invoke_without_command=True)
@click.pass_context
def clients(ctx):
    if ctx.invoked_subcommand is None:
        for client in api.Client.objects.all():
            # TODO: Add option for simple print without colors & machine readable format
            click.echo("{} {}".format(
                client.name,
                click.style("[#{}]".format(client.id), fg="white", dim=1),
            ))


@clients.command('create', short_help='create new client')
@click.option('--name', '-n', prompt='Name of the client',
              help='Specifies the name of the client', )
@click.option('--note', help='Specifies a note linked to the client', )
@click.option('--workspace', '-w', help='Specifies a workspace where the client will be created', )
@click.pass_context
def add_client(ctx, name, note, workspace):
    client = api.Client(name,)


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
