#!/usr/bin/python
"""
toggl.py

Copyright (c) 2014 D. Robert Adams. All rights reserved.
Modified for toggl API v8 by Beau Raines

ASCII art from http://patorjk.com/software/taag/#p=display&c=bash&f=Standard
"""

# NOTES
#
# Actions that need to be refactored:
#  clients
#  projects
#  start DESCR [@PROJECT] [DATETIME]
#  add DESCR [@PROJECT] START_DATETIME ('d'DURATION | END_DATETIME)
#  ls
#  continue DESCR
#  now
#  rm ID
#  stop [DATETIME]
#  www

#
# Negative duration (seconds since epoch) should be in UTC. If you localize it,
# it will be off by however far you are from GMT.
#
# Need to add some sanity checks to TimeEntry().start() and add(). For example
# start() should ensure that duration is negative. add() should ensure duration
# is positive.

import ConfigParser
import datetime
import dateutil.parser
import iso8601
import json
import optparse
import os
import pytz
import requests
import sys
import time
import urllib

TOGGL_URL = "https://www.toggl.com/api/v8"
VERBOSE = False # verbose output?
Parser = None   # OptionParser initialized by main()
VISIT_WWW_COMMAND = "open http://www.toggl.com/app/timer"

#############################################################################
#    _   _ _   _ _ _ _            ____ _                         
#   | | | | |_(_) (_) |_ _   _   / ___| | __ _ ___ ___  ___  ___ 
#   | | | | __| | | | __| | | | | |   | |/ _` / __/ __|/ _ \/ __|
#   | |_| | |_| | | | |_| |_| | | |___| | (_| \__ \__ \  __/\__ \
#    \___/ \__|_|_|_|\__|\__, |  \____|_|\__,_|___/___/\___||___/
#                        |___/                                   
#############################################################################

#----------------------------------------------------------------------------
# Singleton
#----------------------------------------------------------------------------
class Singleton(type):
    """
    Defines a way to implement the singleton pattern in Python.
    From: http://stackoverflow.com/questions/31875/is-there-a-simple-elegant-way-to-define-singletons-in-python/33201#33201

    To use, simply put the following line in your class definition:
        __metaclass__ = Singleton
    """
    def __init__(cls, name, bases, dict):
        super(Singleton, cls).__init__(name, bases, dict)
        cls.instance = None 

    def __call__(cls,*args,**kw):
        if cls.instance is None:
            cls.instance = super(Singleton, cls).__call__(*args, **kw)
        return cls.instance

#----------------------------------------------------------------------------
# Config
#----------------------------------------------------------------------------
class Config(object):
    """
    Singleton. toggl configuration data, read from ~/.togglrc.
    Properties:
        auth - (username, password) tuple.
    """

    __metaclass__ = Singleton

    def __init__(self):
        """
        Reads configuration data from ~/.togglrc.
        """
        self.cfg = ConfigParser.ConfigParser()
        if self.cfg.read(os.path.expanduser('~/.togglrc')) == []:
            self._create_empty_config()
            raise IOError("Missing ~/.togglrc. A default has been created for editing.")

        self.auth = (self.get('auth', 'username'), self.get('auth', 'password'))
    
    def _create_empty_config(self):
        """
        Creates a blank ~/.togglrc.
        """
        cfg = ConfigParser.RawConfigParser()
        cfg.add_section('auth')
        cfg.set('auth', 'username', 'user@example.com')
        cfg.set('auth', 'password', 'toggl_password')
        cfg.add_section('options')
        cfg.set('options', 'timezone', 'UTC')
        cfg.set('options', 'time_format', '%I:%M%p')
        with open(os.path.expanduser('~/.togglrc'), 'w') as cfgfile:
            cfg.write(cfgfile)
        os.chmod(os.path.expanduser('~/.togglrc'), 0600)

    def get(self, section, key):
        """
        Returns the value of the configuration variable identified by the
        given key within the given section of the configuration file. Raises
        ConfigParser exceptions if the section or key are invalid.
        """
        return self.cfg.get(section, key).strip()

#----------------------------------------------------------------------------
# DateAndTime
#----------------------------------------------------------------------------
class DateAndTime(object):
    """
    Singleton date and time functions. Mostly utility functions. All
    the timezone and datetime functionality is localized here.
    """

    __metaclass__ = Singleton

    def __init__(self):
        self.tz = pytz.timezone( Config().get('options', 'timezone') ) 
        self.epoch = self.tz.localize( datetime.datetime(1970, 1, 1) ) 

    def datetime_to_epoch(self, dt):
        """
        Returns the given localizd datetime as the number of seconds since the epoch.
        """
        return (dt - self.epoch).total_seconds()
    
    def duration_str_to_seconds(self, duration_str):
        """
        Parses a string of the form [[Hours:]Minutes:]Seconds and returns
        the total time in seconds.
        """
        elements = duration_str.split(':')
        duration = 0
        if len(elements) == 3:
            duration += int(elements[0]) * 3600
            elements = elements[1:]
        if len(elements) == 2:
            duration += int(elements[0]) * 60
            elements = elements[1:]
        duration += int(elements[0])
        
        return duration

    def elapsed_time(self, seconds, suffixes=['y','w','d','h','m','s'], add_s=False, separator=' '):
        """
        Takes an amount of seconds and turns it into a human-readable amount of time.
        From http://snipplr.com/view.php?codeview&id=5713
        """
        # the formatted time string to be returned
        time = []
        
        # the pieces of time to iterate over (days, hours, minutes, etc)
        # - the first piece in each tuple is the suffix (d, h, w)
        # - the second piece is the length in seconds (a day is 60s * 60m * 24h)
        parts = [(suffixes[0], 60 * 60 * 24 * 7 * 52),
                  (suffixes[1], 60 * 60 * 24 * 7),
                  (suffixes[2], 60 * 60 * 24),
                  (suffixes[3], 60 * 60),
                  (suffixes[4], 60),
                  (suffixes[5], 1)]
        
        # for each time piece, grab the value and remaining seconds, and add it to
        # the time string
        for suffix, length in parts:
            value = seconds / length
            if value > 0:
                seconds = seconds % length
                time.append('%s%s' % (str(value),
                    (suffix, (suffix, suffix + 's')[value > 1])[add_s]))
            if seconds < 1:
                break
        
        return separator.join(time)

    def format_time(self, time):
        """
        Formats the given datetime object according to the strftime() options
        from the configuration file.
        """
        format = Config().get('options', 'time_format')
        return time.strftime(format)

    def last_minute_today(self):
        """
        Returns 23:59:59 today as a localized datetime object.
        """
        return datetime.datetime.now(self.tz) \
            .replace(hour=23, minute=59, second=59, microsecond=0)

    def now(self):
        """
        Returns "now" as a localized datetime object.
        """
        return self.tz.localize( datetime.datetime.now() ) 
 
    def parse_local_datetime_str(self, datetime_str):
        """
        Parses a local datetime string (e.g., "2:00pm") and returns
        a localized datetime object.
        """
        return self.tz.localize( dateutil.parser.parse(datetime_str) )

    def parse_iso_str(self, iso_str):
        """
        Parses an ISO 8601 datetime string and returns a localized datetime 
        object.
        """
        return iso8601.parse_date(iso_str).astimezone(self.tz)

    def start_of_today(self):
        """
        Returns 00:00:00 today as a localized datetime object.
        """
        return self.tz.localize(
            datetime.datetime.combine( datetime.date.today(), datetime.time.min) 
        )

    def start_of_yesterday(self):
        """
        Returns 00:00:00 yesterday as a localized datetime object.
        """
        return self.tz.localize(
            datetime.datetime.combine( datetime.date.today(), datetime.time.min) - 
            datetime.timedelta(days=1) # subtract one day from today at midnight
        )

#----------------------------------------------------------------------------
# Logger 
#----------------------------------------------------------------------------
class Logger(object):
    """
    Custom logger class. Created because I got tired of seeing logging message
    from all the modules imported here. There's no easy way to limit logging
    to this file only.
    """

    # Logging levels.
    NONE = 0
    INFO = 1
    DEBUG = 2

    # Current level.
    level = NONE

    @staticmethod
    def debug(msg, end="\n"):
        """
        Prints msg if the current logging level >= DEBUG.
        """ 
        if Logger.level >= Logger.DEBUG:
            print ("%s%s" % (msg, end)),

    @staticmethod
    def info(msg, end="\n"):
        """
        Prints msg if the current logging level >= INFO.
        """ 
        if Logger.level >= Logger.INFO:
            print ("%s%s" % (msg, end)),

#----------------------------------------------------------------------------
# toggl
#----------------------------------------------------------------------------
def toggl(url, method, data=None, headers={'content-type' : 'application/json'}):
    """
    Makes an HTTP request to toggl.com. Returns the data received from them.
    """
    if method == 'get':
        r = requests.get(url, auth=Config().auth, data=data, headers=headers)
    elif method == 'post':
        r = requests.post(url, auth=Config().auth, data=data, headers=headers)
    else:
        raise NotImplementedError('HTTP method "%s" not implemented.' % method)
    r.raise_for_status() # raise exception on error
    return r.text

#############################################################################
#    _                    _   __  __           _      _     
#   | |_ ___   __ _  __ _| | |  \/  | ___   __| | ___| |___ 
#   | __/ _ \ / _` |/ _` | | | |\/| |/ _ \ / _` |/ _ \ / __|
#   | || (_) | (_| | (_| | | | |  | | (_) | (_| |  __/ \__ \
#    \__\___/ \__, |\__, |_| |_|  |_|\___/ \__,_|\___|_|___/
#             |___/ |___/                                   
#############################################################################

#----------------------------------------------------------------------------
# ClientList
#----------------------------------------------------------------------------
class ClientList(object):
    """
    A list of clients.
    """

    def __init__(self):
        """
        Fetches the list of clients from toggl.
        """
        result = toggl("%s/clients" % TOGGL_URL, 'get')
        self.client_list = json.loads(result)

    def __iter__(self):
        """
        Start iterating over the clients.
        """
        self.iter_index = 0
        return self

    def next(self):
        """
        Returns the next client.
        """
        if self.iter_index >= len(self.client_list):
            raise StopIteration
        else:
            self.iter_index += 1
            return self.client_list[self.iter_index-1]

    def __str__(self):
        """
        Formats the list of clients as a string.
        """
        s = ""
        for client in self.client_list:
            s = s + "%s\n" % client['name']
        return s.rstrip() # strip trailing \n

#----------------------------------------------------------------------------
# ProjectList
#----------------------------------------------------------------------------
class ProjectList(object):
    """
    A list of projects. A "project object" is a dictionary as documented
    at https://github.com/toggl/toggl_api_docs/blob/master/chapters/projects.md
    """

    def __init__(self):
        """
        Fetches the list of projects from toggl.
        """
        result = toggl("%s/workspaces/%s/projects" % (TOGGL_URL, User().default_wid), 'get')
        self.project_list = json.loads(result)

    def find_by_id(self, pid):
        """
        Returns the project object with the given id, or None.
        """
        for project in self:
            if project['id'] == pid:
                return project
        return None

    def find_by_name(self, name_prefix):
        """
        Returns the project object with the given name (or prefix), or None.
        """
        for project in self:
            if project['name'].startswith(name_prefix):
                return project
        return None

    def __iter__(self):
        """
        Start iterating over the projects.
        """
        self.iter_index = 0
        return self

    def next(self):
        """
        Returns the next project.
        """
        if self.iter_index >= len(self.project_list):
            raise StopIteration
        else:
            self.iter_index += 1
            return self.project_list[self.iter_index-1]

    def __str__(self):
        """Formats the project list as a string."""
        s = ""
        clients = ClientList()
        for project in self:
            client_name = ''
            if 'cid' in project:
               for client in clients:
                   if project['cid'] == client['id']:
                       client_name = " - %s" % client['name']
            s = s + "@%s%s\n" % (project['name'], client_name)
        return s.rstrip() # strip trailing \n

#----------------------------------------------------------------------------
# TimeEntry
#----------------------------------------------------------------------------
class TimeEntry(object):
    """
    Represents a single toggl time entry. An entry can represent a completed
    time entry, or a currently running entry on depending on the values of
    the duration and end_time properties.

    NB: If duration is negative, it represents the amount of elapsed time
    since the epoch. It's not well documented, but toggl expects this duration
    to be in UTC.
    """

    def __init__(self, description, start_time, project_name=None):
        """
        Constructor. description(str) is the time entry description,
        project_name(str) is the optional name of the project without the @ prefix.
        start_time(datetime) is the time this entry started.
        end_time(datetime) is the optional time this entry was stopped.
        """
        self.start_time = start_time # start time in datetime format
        self.project_name = project_name 

        self.data = {}  # toggl time entry data
        self.data['description'] = description
        self.data['start'] = start_time.isoformat()
        self.data['billable'] = False
        self.data['created_with'] = 'toggl-cli'

        if project_name != None:
            # Look up the project from toggl to get the id.
            project = ProjectList().find_by_name(project_name)
            if project == None:
                raise RuntimeError("Project '%s' not found." % project_name)
            self.data['pid'] = project['id']

    def add(self):
        """
        Adds this time entry as a completed entry.
        """
        try:
            Logger.debug(str(self))
            r = requests.post("%s/time_entries" % TOGGL_URL, 
                auth=Config().auth,
                data=self.json(), 
                headers={'content-type': 'application/json'}
            )
            r.raise_for_status() # raise exception on error
        except requests.HTTPError:
            print 'Sent: ' + self.json()
            print 'Received: ' + r.text
            
    def json(self):
        """
        Returns a JSON dump of this entire object as toggl payload.
        """
        return '{"time_entry": %s}' % json.dumps(self.data)

    def start(self):
        """
        Starts this time entry by telling toggl.
        """
        self.data['duration'] = 0 - DateAndTime().datetime_to_epoch(self.start_time)

        try:
            Logger.debug(str(self))
            r = requests.post("%s/time_entries" % TOGGL_URL, 
                auth=Config().auth,
                data=self.json(), 
                headers={'content-type': 'application/json'}
            )
            r.raise_for_status() # raise exception on error
        except requests.HTTPError:
            print 'Sent: ' + self
            print 'Received: ' + r.text
        else:
            Logger.info('%s started at %s' % (self.data['description'], DateAndTime().format_time(self.start_time)))

    def set(self, prop, value):
        """
        Sets the given toggl time entry property to the given value. Properties
        are documented at 
        https://github.com/toggl/toggl_api_docs/blob/master/chapters/time_entries.md
        """
        self.data[prop] = value

    def __str__(self):
        """
        Returns a human-friendly string representation of this time entry.
        """
        # Make a human-friendly elapsed time.
        elapsed_seconds = 0
        if self.data['duration'] > 0:
            is_running = '  '
            elapsed_seconds = int(self.data['duration'])
        else:
            is_running = '* '
            elapsed_seconds = time.time() + int(self.data['duration'])
        elapsed_time_str = "%s" % DateAndTime().elapsed_time(int(elapsed_seconds), separator='')
        
        # Get the project name, if it exists.
        if self.project_name is not None:
            project_name = " @%s " % self.project_name 
        else:
            project_name = " "

        s = "%s%s%s%s" % (is_running, self.data['description'], project_name, elapsed_time_str)

        if VERBOSE:
            s += " [%s]" % self.data['id']

        return s

#----------------------------------------------------------------------------
# User
#----------------------------------------------------------------------------
class User(object):
    """
    Singleon. Toggl user data.
    """

    __metaclass__ = Singleton

    def __init__(self):
        """
        Fetches user data from toggl.
        """
        result = toggl("%s/me" % TOGGL_URL, 'get')
        self.__dict__['user_data'] = json.loads(result)

    def __getattr__(self, property):
        """
        Usage: User().PROPERTY
        Return the given toggl user property. User properties are
        documented at https://github.com/toggl/toggl_api_docs/blob/master/chapters/users.md
        """
        if property == 'since': # 'since' lives at the root of the user_data dict.
            return self.__dict__['user_data']['since']
        elif property in self.__dict__['user_data']['data']:
            return self.__dict__['user_data']['data'][property]
        else:
            raise AttributeError("toggl user object has no property '%s'" % property)

#############################################################################
#     ____                                          _   _     _            
#    / ___|___  _ __ ___  _ __ ___   __ _ _ __   __| | | |   (_)_ __   ___ 
#   | |   / _ \| '_ ` _ \| '_ ` _ \ / _` | '_ \ / _` | | |   | | '_ \ / _ \
#   | |__| (_) | | | | | | | | | | | (_| | | | | (_| | | |___| | | | |  __/
#    \____\___/|_| |_| |_|_| |_| |_|\__,_|_| |_|\__,_| |_____|_|_| |_|\___|
#                                                                          
#############################################################################

#----------------------------------------------------------------------------
# CLI
#----------------------------------------------------------------------------
class CLI(object):
    """
    Singleton class to process command-line actions.
    """
    __metaclass__ = Singleton

    def __init__(self):
        """
        Initializes the command-line parser and handles the command-line options.
        """

        # Override the option parser epilog formatting rule.
        # See http://stackoverflow.com/questions/1857346/python-optparse-how-to-include-additional-info-in-usage-output
        optparse.OptionParser.format_epilog = lambda self, formatter: self.epilog
        
        self.parser = optparse.OptionParser(usage="Usage: %prog [OPTIONS] [ACTION]", \
            epilog="\nActions:\n"
            "  add DESCR [@PROJECT] START_DATETIME ('d'DURATION | END_DATETIME)\n\tcreates a completed time entry\n"
            "  clients\n\tlists all clients\n"
            "  continue DESCR\n\trestarts the given entry\n"
            "  ls\n\tlist recent time entries\n"
            "  now\n\tprint what you're working on now\n"
            "  projects\n\tlists all projects\n"
            "  rm ID\n\tdelete a time entry by id\n"
            "  start DESCR [@PROJECT] [DATETIME]\n\tstarts a new entry\n"
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
        (options, self.args) = self.parser.parse_args()

        # Process command-line options.
        Logger.level = Logger.INFO
        if options.quiet:
            Logger.level = Logger.NONE
        if options.debug:
            Logger.level = Logger.DEBUG
        if options.verbose:
            global VERBOSE 
            VERBOSE = True

    def add_time_entry(self, args):
        """
        Creates a completed time entry.
        args should be: DESCR [@PROJECT] START_DATE_TIME 'd'DURATION | END_DATE_TIME
        """
        # Process the args.
        description = self.get_str_arg(args)

        project_name = self.get_project_arg(args, optional=True)
        if project_name is not None:
            project = ProjectList().find_by_name(project_name)
            if project == None:
                raise RuntimeError("Project '%s' not found." % project_name)

        start_time = self.get_datetime_arg(args, optional=False)
        end_time = None
        duration = self.get_duration_arg(args, optional=True)
        if duration is None:
            end_time = self.get_datetime_arg(args, optional=False)
            duration = (end_time - start_time).seconds

        # Create a time entry.
        entry = TimeEntry(description, start_time, project_name)
        entry.set('duration', duration)
        if end_time is not None:
            entry.set('stop', end_time.isoformat())

        entry.add()
        Logger.info('%s added' % description)
        
    def act(self):
        """
        Performs the actions described by the list of arguments in self.args.
        """
        if len(self.args) == 0 or self.args[0] == "ls":
            return list_time_entries()
        elif self.args[0] == "add":
            self.add_time_entry(self.args[1:])
        elif self.args[0] == "clients":
            print ClientList()
        elif self.args[0] == "continue":
            return continue_entry(self.args[1:])
        elif self.args[0] == "now":
            return list_current_time_entry()
        elif self.args[0] == "projects":
            print ProjectList()
        elif self.args[0] == "rm":
            return delete_time_entry(self.args[1:])
        elif self.args[0] == "start":
            self.start_time_entry(self.args[1:])
        elif self.args[0] == "stop":
            if len(self.args) > 1:
                return stop_time_entry(self.args[1:])
            else:
                return stop_time_entry()
        elif self.args[0] == "www":
            os.system(VISIT_WWW_COMMAND)	
        else:
            self.print_help()

    def get_datetime_arg(self, args, optional=False):
        """
        Returns args[0] as a localized datetime object, or None.
        """
        if len(args) == 0:
            if optional:
                return None
            else:
                self.print_help()
        else:
            return DateAndTime().parse_local_datetime_str(args.pop(0))

    def get_duration_arg(self, args, optional=False):
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
            return DateAndTime().duration_str_to_seconds( args.pop(0)[1:] )

    def get_project_arg(self, args, optional=False):
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

    def get_str_arg(self, args, optional=False):
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

    def print_help(self):
        """Prints the usage message and exits."""
        self.parser.print_help()
        sys.exit(1)

    def start_time_entry(self, args):
        """
           Starts a new time entry.
           args should be: DESCR [@PROJECT] [DATETIME]
        """
        description = self.get_str_arg(args, optional=False)
        project_name = self.get_project_arg(args, optional=True)
        start_time = self.get_datetime_arg(args, optional=True)
        if start_time is None:
            start_time = DateAndTime().now()

        # Create the time entry.
        entry = TimeEntry(description, start_time, project_name)
        entry.start()
        
#############################################################################
# Still needs to be refactored.
#############################################################################

def continue_entry(args):
    """Continues a time entry. args[0] should be the description of the entry
    to restart. Assumes that the entry appears in the list returned by
    get_time_entry_data()."""

# Continuing an entry from earlier today, then stopping it sometimes (always?) messes up the time. It seems
# to count the entire interval from when it was first stopped until the continuation stopped.

    if len(args) == 0:
        CLI().print_help()

    description = args[0]

    entries = get_time_entry_data()

    # There may be multiple entries with the same description. We restart
    # the most recent one by iterating through the responses backwards
    # (newest to oldest), and restart the first one we find.
    for entry in reversed(entries):
	if str(entry['description']) == description:

            # Check when the entry was started, today or previously?
            start_time = DateAndTime().parse_iso_str(entry['start'])
            if start_time <= DateAndTime().start_of_today():
                # If the entry was from a previous day, then we simply start
                # a new entry.
                TimeEntry(description, 
                    ProjectList().find_by_id(entry['pid'])['name'],
                    DateAndTime().now()
                ).start()
            else:
                # To continue an entry from today, set duration to 
                # 0-(current_time-duration).
                entry['duration'] = 0-(time.time()-int(entry['duration']))
                entry['duronly'] = True # ignore start/stop times from now on

                # Send the data.
                headers = {'content-type': 'application/json'}
                r = requests.put("%s/time_entries/%s" % (TOGGL_URL, entry['id']), 
                    auth=Config().auth, 
                    data='{"time_entry":%s}' % json.dumps(entry), headers=headers)
                r.raise_for_status() # raise exception on error

                Logger.info("%s continued at %s" % (description, DateAndTime().format_time(datetime.datetime.now())))

                Logger.debug(json.dumps(entry))

            return 0

    raise RuntimeError("Did not find '%s' in list of entries." % description)

#----------------------------------------------------------------------------
def delete_time_entry(args):
    if len(args) == 0:
        Parser.print_help()
        return 1

    entry_id = args[0]

    response = get_time_entry_data()

    for entry in response:
	if str(entry['id']) == entry_id:
            Logger.info("Deleting entry " + entry_id)

            headers = {'content-type': 'application/json'}
            r = requests.delete("%s/time_entries/%s" % (TOGGL_URL, entry_id), auth=Config().auth,
                data=None, headers=headers)
            r.raise_for_status() # raise exception on error

    return 0
    
#----------------------------------------------------------------------------
def get_current_time_entry():
    """Returns the current time entry JSON object, or None."""
    response = get_time_entry_data()
    
    for entry in response:
        if int(entry['duration']) < 0:
            return entry
    
    return None

#----------------------------------------------------------------------------
def get_time_entry_data():
    """Fetches time entry data and returns it as a Python array."""

    # Fetch time entries from 00:00:00 yesterday to 23:59:59 today.
    url = "%s/time_entries?start_date=%s&end_date=%s" % \
        (TOGGL_URL, urllib.quote(DateAndTime().start_of_yesterday().isoformat('T')), \
        urllib.quote(DateAndTime().last_minute_today().isoformat('T')))

    Logger.debug(url)
    r = requests.get(url, auth=Config().auth)
    r.raise_for_status() # raise exception on error
    Logger.debug(r.text)
    
    return json.loads(r.text)

#----------------------------------------------------------------------------
def list_current_time_entry():
    """Shows what the user is currently working on."""
    entry = get_current_time_entry()

    if entry != None:
	# Lookup the project name, if it exists.
    	if 'pid' in entry:
            entry['project_name'] = '@' + ProjectList().find_by_id(entry['pid'])['name']
        print_time_entry(entry)
    else:
        Logger.info("You're not working on anything right now.")
    
    return 0

#----------------------------------------------------------------------------
def list_time_entries():
	"""Lists all of the time entries from yesterday and today along with
	   the amount of time devoted to each.
	"""

	# Get an array of objects of recent time data.
	response = get_time_entry_data()

	# Sort the time entries into buckets based on "Month Day" of the entry.
	days = { }
        projects = ProjectList()
	for entry in response:
		start_time = DateAndTime().parse_iso_str(entry['start']).strftime("%b %d")
		if start_time not in days:
			days[start_time] = []
		days[start_time].append(entry)
                # If the entry has a project, get it's name.
    		if 'pid' in entry:
	            entry['project_name'] = '@' + projects.find_by_id(entry['pid'])['name']

	# For each day, print the entries, then sum the times.
	for date in sorted(days.keys()):
            Logger.info(date)
            duration = 0
            for entry in days[date]:
                    Logger.info("  ", end="")
                    duration += print_time_entry(entry)
            Logger.info("   (%s)" % DateAndTime().elapsed_time(int(duration)))

	return 0

#----------------------------------------------------------------------------
def print_time_entry(entry):
    """Utility function to print a time entry object and returns the
	   integer duration for this entry."""
    
    # If the duration is negative, the entry is currently running so we
    # have to calculate the duration by adding the current time.
    is_running = ''
    e_time = 0
    if entry['duration'] > 0:
        e_time = int(entry['duration'])
    else:
        is_running = '*'
        e_time = time.time() + int(entry['duration'])
    e_time_str = "%s" % DateAndTime().elapsed_time(int(e_time), separator='')
    
    Logger.info(is_running, end="")
    Logger.info(entry['description'], end="")
    if 'project_name' in entry:
        Logger.info(entry['project_name'], end="")
    Logger.info(e_time_str, end="")

    if VERBOSE:
        Logger.info("[%s]" % entry['id'])
    else:
        Logger.info("")

    return e_time

#----------------------------------------------------------------------------
def stop_time_entry(args=None):
    """
    Stops the current time entry (duration is currently negative).
    args contains an optional end time.
    """

    entry = get_current_time_entry()
    if entry != None:
        # Get the start time from the entry.
        start_time = DateAndTime().parse_iso_str(entry['start'])

        if args != None and len(args) == 1:
	    stop_time = DateAndTime().parse_local_datetime_str(args[0])
        else:
            # Get stop time (now) in UTC.
            stop_time = DateAndTime().now()

        # Create the payload.
        data = { 'time_entry' : entry }
        data['time_entry']['stop'] = stop_time.isoformat()
        data['time_entry']['duration'] = (stop_time - start_time).seconds

        url = "%s/time_entries/%d" % (TOGGL_URL, entry['id'])

        Logger.debug(url)
        Logger.debug(json.dumps(data))

        headers = {'content-type': 'application/json'}
        r = requests.put(url, auth=Config().auth, data=json.dumps(data), headers=headers)
        r.raise_for_status() # raise exception on error

        Logger.info('%s stopped at %s' % (entry['description'], DateAndTime().format_time(stop_time)))
    else:
        Logger.info("You're not working on anything right now.")
        return 1

    return 0

if __name__ == "__main__":
    CLI().act()
    sys.exit(0)
