import datetime
import optparse
import os
import sys

from . import api, utils


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
        optparse.OptionParser.format_epilog = lambda self, formatter: self.epilog

        self.parser = optparse.OptionParser(usage="Usage: %prog [OPTIONS] [ACTION]", \
                                            epilog="\nActions:\n"
                                                   "  add DESCR [:WORKSPACE] [@PROJECT] START_DATETIME ('d'DURATION | END_DATETIME)\n\tcreates a completed time entry\n"
                                                   "  add DESCR [:WORKSPACE] [@PROJECT] 'd'DURATION\n\tcreates a completed time entry, with start time DURATION ago\n"
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
                                                   "  DURATION = [[Hours:]Minutes:]Seconds\n")
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
            if workspace == None:
                raise RuntimeError("Workspace '{}' not found.".format(workspace_name))
            else:
                ws_name = workspace["name"]
        project_name = self._get_project_arg(args, optional=True)
        if project_name is not None:
            project = api.ProjectList(ws_name).find_by_name(project_name)
            if project == None:
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
                        if (duration is not None):
                            continued_at = utils.DateAndTime().now() - datetime.timedelta(seconds=duration)
                        else:
                            continued_at = self._get_datetime_arg(args, optional=True)
                else:
                    self._show_continue_usage()
                    return

            entry.continue_entry(continued_at)

            utils.Logger.info("{} continued at {}".format(entry.get('description'),
                                                    utils.DateAndTime().format_time(continued_at or utils.DateAndTime().now())))
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

        if entry != None:
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
        if entry != None:
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
