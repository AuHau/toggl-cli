#!/usr/bin/env python
"""
toggl.py

Copyright (c) 2014 D. Robert Adams. All rights reserved.
Modified for toggl API v8 by Beau Raines

ASCII art from http://patorjk.com/software/taag/#p=display&c=bash&f=Standard
"""

# This file is divided into three main parts.
#   1. Utility Classes - generic support code
#   2. Toggl Models - Toggl-specific data classes
#   3. Command Line Interface - CLI

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
import six
from six.moves import urllib
from six.moves import configparser as ConfigParser

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

    def _create_empty_config(self):
        """
        Creates a blank ~/.togglrc.
        """
        cfg = ConfigParser.RawConfigParser()
        cfg.add_section('auth')
        cfg.set('auth', 'username', 'user@example.com')
        cfg.set('auth', 'password', 'toggl_password')
        cfg.set('auth', 'api_token', 'your_api_token')
        cfg.add_section('options')
        cfg.set('options', 'timezone', 'UTC')
        cfg.set('options', 'time_format', '%I:%M%p')
        cfg.set('options', 'prefer_token', 'true')
        with open(os.path.expanduser('~/.togglrc'), 'w') as cfgfile:
            cfg.write(cfgfile)
        os.chmod(os.path.expanduser('~/.togglrc'), 0o600)

    def get(self, section, key):
        """
        Returns the value of the configuration variable identified by the
        given key within the given section of the configuration file. Raises
        ConfigParser exceptions if the section or key are invalid.
        """
        return self.cfg.get(section, key).strip()

    def get_auth(self):
        if self.get('options', 'prefer_token').lower() == 'true':
            return requests.auth.HTTPBasicAuth(self.get('auth', 'api_token'),
                                               'api_token')
        else:
            return requests.auth.HTTPBasicAuth(self.get('auth', 'username'),
                                               self.get('auth', 'password'))

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

    def duration_since_epoch(self, dt):
        """
        Converts the given localized datetime object to the number of 
        seconds since the epoch.
        """
        return (dt.astimezone(pytz.UTC) - datetime.datetime(1970,1,1,tzinfo=pytz.UTC)).total_seconds()

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

    def elapsed_time(self, seconds, suffixes=['y','w','d','h','m','s'], add_s=False, separator=''):
        """
        Takes an amount of seconds and turns it into a human-readable amount
        of time.
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
            value = seconds // length
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
            print("%s%s" % (msg, end)),

    @staticmethod
    def info(msg, end="\n"):
        """
        Prints msg if the current logging level >= INFO.
        """ 
        if Logger.level >= Logger.INFO:
            print("%s%s" % (msg, end)),

#----------------------------------------------------------------------------
# toggl
#----------------------------------------------------------------------------
def toggl(url, method, data=None, headers={'content-type' : 'application/json'}):
    """
    Makes an HTTP request to toggl.com. Returns the raw text data received.
    """
    try:
        if method == 'delete':
            r = requests.delete(url, auth=Config().get_auth(), data=data, headers=headers)
        elif method == 'get':
            r = requests.get(url, auth=Config().get_auth(), data=data, headers=headers)
        elif method == 'post':
            r = requests.post(url, auth=Config().get_auth(), data=data, headers=headers)
        elif method == 'put':
            r = requests.post(url, auth=Config().get_auth(), data=data, headers=headers)
        else:
            raise NotImplementedError('HTTP method "%s" not implemented.' % method)
        r.raise_for_status() # raise exception on error
        return r.text
    except Exception as e:
        print('Sent: %s' % data)
        print(e)
        print(r.text)
        #sys.exit(1)

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
    A singleton list of clients. A "client object" is a set of properties
    as documented at 
    https://github.com/toggl/toggl_api_docs/blob/master/chapters/clients.md
    """

    __metaclass__ = Singleton

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
        return s.rstrip().encode('utf-8') # strip trailing \n

#----------------------------------------------------------------------------
# WorkspaceList
#----------------------------------------------------------------------------
class WorkspaceList(six.Iterator):
    """
    A singleton list of workspace. A workspace object is a dictionary as
    documented at
    https://github.com/toggl/toggl_api_docs/blob/master/chapters/workspaces.md
    """

    __metaclass__ = Singleton

    def __init__(self):
        """
        Fetches the list of workspaces from toggl.
        """
        result = toggl("%s/workspaces" % TOGGL_URL, "get")
        self.workspace_list = json.loads(result)

    def find_by_id(self, wid):
        """
        Returns the workspace object with the given id, or None.
        """
        for workspace in self:
            if workspace['id'] == wid:
                return workspace
        return None

    def find_by_name(self, name_prefix):
        """
        Returns the workspace object with the given name (or prefix), or None.
        """
        for workspace in self:
            if workspace['name'].startswith(name_prefix):
                return workspace
        return None

    def __iter__(self):
        """
        Start iterating over the workspaces.
        """
        self.iter_index = 0
        return self

    def __next__(self):
        """
        Returns the next workspace.
        """
        if self.iter_index >= len(self.workspace_list):
            raise StopIteration
        else:
            self.iter_index += 1
            return self.workspace_list[self.iter_index-1]

    def __str__(self):
        """Formats the project list as a string."""
        s = ""
        for workspace in self:
            s = s + ":%s\n" % workspace['name']
        return s.rstrip() # strip trailing \n
#----------------------------------------------------------------------------
# ProjectList
#----------------------------------------------------------------------------
class ProjectList(six.Iterator):
    """
    A singleton list of projects. A "project object" is a dictionary as 
    documented at 
    https://github.com/toggl/toggl_api_docs/blob/master/chapters/projects.md
    """

    __metaclass__ = Singleton

    def __init__(self, workspace_name = None):
        self.fetch(workspace_name)

    def fetch(self, workspace_name = None):
        """
        Fetches the list of projects from toggl.
        """
        wid = None
        if workspace_name is not None:
            self.workspace = WorkspaceList().find_by_name(workspace_name)
            if self.workspace is not None:
                wid = self.workspace["id"]
        if wid is None:
                wid = User().get('default_wid')
                self.workspace = WorkspaceList().find_by_id(wid)

        result = toggl("%s/workspaces/%s/projects" % (TOGGL_URL, wid), 'get')
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

    def __next__(self):
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
            s = s + ":%s @%s%s\n" % (self.workspace['name'], project['name'], client_name)
        return s.rstrip() # strip trailing \n

#----------------------------------------------------------------------------
# TimeEntry
#----------------------------------------------------------------------------
class TimeEntry(object):
    """
    Represents a single time entry. 

    NB: If duration is negative, it represents the amount of elapsed time
    since the epoch. It's not well documented, but toggl expects this duration
    to be in UTC.
    """

    def __init__(self, description=None, start_time=None, stop_time=None,
                 duration=None, workspace_name = None, project_name=None,
                 data_dict=None):
        """
        Constructor. None of the parameters are required at object creation,
        but the object is validated before data is sent to toggl.
        * description(str) is the optional time entry description. 
        * start_time(datetime) is the optional time this entry started. 
        * stop_time(datetime) is the optional time this entry ended.
        * duration(int) is the optional duration, in seconds. 
        * project_name(str) is the optional name of the project without 
          the '@' prefix.
        * data_dict is an optional dictionary created from a JSON-encoded time
          entry from toggl. If this parameter is used to initialize the object,
          its values will supercede any other constructor parameters. 
        """

        # All toggl data is stored in the "data" dictionary.
        self.data = {} 

        if description is not None:
            self.data['description'] = description

        if start_time is not None:
            self.data['start'] = start_time.isoformat()

        if stop_time is not None:
            self.data['stop'] = stop_time.isoformat()

        if workspace_name is not None:
            workspace = WorkspaceList().find_by_name(workspace_name)
            if workspace == None:
                raise RuntimeError("Workspace '%s' not found." % workspace_name)
            self.data['wid'] = workspace['id']

        if project_name is not None:
            project = ProjectList(workspace_name).find_by_name(project_name)
            if project == None:
                raise RuntimeError("Project '%s' not found." % project_name)
            self.data['pid'] = project['id']

        if duration is not None:
            self.data['duration'] = duration

        # If we have a dictionary of data, use it to initialize this.
        if data_dict is not None:
            self.data = data_dict
       
        self.data['created_with'] = 'toggl-cli'

    def add(self):
        """
        Adds this time entry as a completed entry. 
        """
        self.validate()
        toggl("%s/time_entries" % TOGGL_URL, "post", self.json())

    def continue_entry(self):
        """
        Continues an existing entry.
        """
        # Was the entry started today or earlier than today?
        start_time = DateAndTime().parse_iso_str( self.get('start') )

        if start_time <= DateAndTime().start_of_today():
            # Entry was from a previous day. Create a new entry from this
            # one, resetting any identifiers or time data.
            new_entry = TimeEntry()
            new_entry.data = self.data.copy()
            new_entry.set('at', None)
            new_entry.set('created_with', 'toggl-cli') 
            new_entry.set('duration', None)
            new_entry.set('duronly', False) 
            new_entry.set('guid', None)
            new_entry.set('id', None) 
            new_entry.set('start', None)
            new_entry.set('stop', None)
            new_entry.set('uid', None)
            new_entry.start()
        else:
            # To continue an entry from today, set duration to 
            # 0 - (current_time - duration).
            now = DateAndTime().duration_since_epoch( DateAndTime().now() )
            self.data['duration'] = 0 - (now - int(self.data['duration']))
            self.data['duronly'] = True # ignore start/stop times from now on

            toggl("%s/time_entries/%s" % (TOGGL_URL, self.data['id']), 'put', data=self.json())

            Logger.debug('Continuing entry %s' % self.json())

    def delete(self):
        """
        Deletes this time entry from the server.
        """
        if not self.has('id'):
            raise Exception("Time entry must have an id to be deleted.")

        url = "%s/time_entries/%s" % (TOGGL_URL, self.get('id'))
        toggl(url, 'delete')
        
    def get(self, prop):
        """
        Returns the given toggl time entry property as documented at 
        https://github.com/toggl/toggl_api_docs/blob/master/chapters/time_entries.md
        or None, if the property isn't set.
        """
        if prop in self.data:
            return self.data[prop]
        else:
            return None

    def has(self, prop):
        """
        Returns True if this time entry has the given property and it's not
        None, False otherwise.
        """
        return prop in self.data and self.data[prop] is not None
            
    def json(self):
        """
        Returns a JSON dump of this entire object as toggl payload.
        """
        return '{"time_entry": %s}' % json.dumps(self.data)

    def normalized_duration(self):
        """
        Returns a "normalized" duration. If the native duration is positive, 
        it is simply returned. If negative, we return current_time + duration 
        (the actual amount of seconds this entry has been running). If no
        duration is set, raises an exception.
        """
        if 'duration' not in self.data:
            raise Exception('Time entry has no "duration" property')
        if self.data['duration'] > 0:
            return int(self.data['duration'])
        else:
            return time.time() + int(self.data['duration'])

    def set(self, prop, value):
        """
        Sets the given toggl time entry property to the given value. If 
        value is None, the property is removed from this time entry.
        Properties are documented at 
        https://github.com/toggl/toggl_api_docs/blob/master/chapters/time_entries.md
        """
        if value is not None:
            self.data[prop] = value
        elif prop in self.data:
            self.data.pop(prop)

    def start(self):
        """
        Starts this time entry by telling toggl. If this entry doesn't have
        a start time yet, it is set to now. duration is set to
        0-start_time.
        """
        if self.has('start'):
            start_time = DateAndTime().parse_iso_str(self.get('start'))
            self.set('duration', 0-DateAndTime().duration_since_epoch(start_time))

            self.validate()

            toggl("%s/time_entries" % TOGGL_URL, "post", self.json())
        else:
            # 'start' is ignored by 'time_entries/start' endpoint. We define it
            # to keep consinstency with toggl server
            self.data['start'] = DateAndTime().now().isoformat()

            toggl("%s/time_entries/start" % TOGGL_URL, "post", self.json())

        Logger.debug('Started time entry: %s' % self.json())

    def stop(self, stop_time=None):
        """
        Stops this entry. Sets the stop time at the datetime given, calculates
        a duration, then updates toggl.
        stop_time(datetime) is an optional datetime when this entry stopped. If
        not given, then stops the time entry now.
        """
        Logger.debug('Stopping entry %s' % self.json())
        self.validate()
        if int(self.data['duration']) >= 0:
            raise Exception("toggl: time entry is not currently running.")
        if 'id' not in self.data:
            raise Exception("toggl: time entry must have an id.")

        if stop_time is None:
            stop_time = DateAndTime().now()
        self.set('stop', stop_time.isoformat())
        self.set('duration', \
            DateAndTime().duration_since_epoch(stop_time) + int(self.get('duration')))

        toggl("%s/time_entries/%d" % (TOGGL_URL, self.get('id')), 'put', self.json())

    def __str__(self):
        """
        Returns a human-friendly string representation of this time entry.
        """
        if self.data['duration'] > 0:
            is_running = '  '
        else:
            is_running = '* '
        
        if 'pid' in self.data:
            project_name = " @%s " % ProjectList().find_by_id(self.data['pid'])['name']
        else:
            project_name = " "

        s = "%s%s%s%s" % (is_running, self.data.get('description'), project_name, 
            DateAndTime().elapsed_time(int(self.normalized_duration())) \
        )

        if VERBOSE:
            s += " [%s]" % self.data['id']

        return s

    def validate(self):
        """
        Ensure this time entry contains the minimum information required
        by toggl, as well as passing some basic sanity checks. If not,
        an exception is raised.

        * toggl requires start, duration, and created_with.
        * toggl doesn't require a description, but we do.
        """
        for prop in [ 'start', 'duration', 'description', 'created_with' ]:
            if not self.has(prop):
                Logger.debug(self.json())
                raise Exception("toggl: time entries must have a '%s' property." % prop)
        return True

#----------------------------------------------------------------------------
# TimeEntryList
#----------------------------------------------------------------------------
class TimeEntryList(object):
    """
    A singleton list of recent TimeEntry objects.
    """

    __metaclass__ = Singleton

    def __init__(self):
        """
        Fetches time entry data from toggl.
        """
        self.reload()
        
    def __iter__(self):
        """
        Start iterating over the time entries.
        """
        self.iter_index = 0
        return self

    def find_by_description(self, description):
        """
        Searches the list of entries for the one matching the given 
        description, or return None. If more than one entry exists
        with a matching description, the most recent one is
        returned.
        """
        for entry in reversed(self.time_entries):
            if entry.get('description') == description:
                return entry
        return None

    def next(self):
        """
        Returns the next time entry object.
        """
        if self.iter_index >= len(self.time_entries):
            raise StopIteration
        else:
            self.iter_index += 1
            return self.time_entries[self.iter_index-1]
    
    def now(self):
        """
        Returns the current time entry object or None.
        """
        for entry in self:
            if int(entry.get('duration')) < 0:
                return entry
        return None

    def reload(self):
        """
        Force reloading time entry data from the server. Returns self for
        method chaining.
        """
        # Fetch time entries from 00:00:00 yesterday to 23:59:59 today.
        url = "%s/time_entries?start_date=%s&end_date=%s" % \
            (TOGGL_URL, urllib.parse.quote(DateAndTime().start_of_yesterday().isoformat('T')), \
            urllib.parse.quote(DateAndTime().last_minute_today().isoformat('T')))
        Logger.debug(url)
        entries = json.loads( toggl(url, 'get') )

        # Build a list of entries.
        self.time_entries = []
        for entry in entries:
            te = TimeEntry(data_dict=entry)
            Logger.debug(te.json())
            Logger.debug('---')
            self.time_entries.append(te)

        # Sort the list by start time.
        sorted(self.time_entries, key=lambda entry: entry.data['start'])
        return self

    def __str__(self):
        """
        Returns a human-friendly list of recent time entries.
        """
        # Sort the time entries into buckets based on "Month Day" of the entry.
        days = { }
        for entry in self.time_entries:
            start_time = DateAndTime().parse_iso_str(entry.get('start')).strftime("%Y-%m-%d")
            if start_time not in days:
                days[start_time] = []
            days[start_time].append(entry)

        # For each day, print the entries, and sum the times.
        s = ""
        for date in sorted(days.keys()):
            s += date + "\n"
            duration = 0
            for entry in days[date]:
                s += str(entry) + "\n"
                duration += entry.normalized_duration()
            s += "  (%s)\n" % DateAndTime().elapsed_time(int(duration))
        return s.rstrip() # strip trailing \n
    
#----------------------------------------------------------------------------
# User
#----------------------------------------------------------------------------
class User(object):
    """
    Singleton toggl user data.
    """

    __metaclass__ = Singleton

    def __init__(self):
        """
        Fetches user data from toggl.
        """
        result = toggl("%s/me" % TOGGL_URL, 'get')
        result_dict = json.loads(result)

        # Results come back in two parts. 'since' is how long the user has
        # had their toggl account. 'data' is a dictionary of all the other
        # user data.
        self.data = result_dict['data']
        self.data['since'] = result_dict['since']

    def get(self, prop):
        """
        Return the given toggl user property. User properties are
        documented at https://github.com/toggl/toggl_api_docs/blob/master/chapters/users.md
        """
        return self.data[prop]

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
        Initializes the command-line parser and handles the command-line 
        options.
        """

        # Override the option parser epilog formatting rule.
        # See http://stackoverflow.com/questions/1857346/python-optparse-how-to-include-additional-info-in-usage-output
        optparse.OptionParser.format_epilog = lambda self, formatter: self.epilog
        
        self.parser = optparse.OptionParser(usage="Usage: %prog [OPTIONS] [ACTION]", \
            epilog="\nActions:\n"
            "  add DESCR [:WORKSPACE] [@PROJECT] START_DATETIME ('d'DURATION | END_DATETIME)\n\tcreates a completed time entry\n"
            "  clients\n\tlists all clients\n"
            "  continue DESCR\n\trestarts the given entry\n"
            "  ls\n\tlist recent time entries\n"
            "  now\n\tprint what you're working on now\n"
            "  workspaces\n\tlists all workspaces\n"
            "  projects [:WORKSPACE]\n\tlists all projects\n"
            "  rm ID\n\tdelete a time entry by id\n"
            "  start DESCR [:WORKSPACE] [@PROJECT] [DATETIME]\n\tstarts a new entry\n"
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

    def _add_time_entry(self, args):
        """
        Creates a completed time entry.
        args should be: DESCR [:WORKSPACE] [@PROJECT] START_DATE_TIME
            'd'DURATION | STOP_DATE_TIME
        """
        # Process the args.
        description = self._get_str_arg(args)
        workspace_name = self._get_workspace_arg(args, optional=True)
        ws_name = None # canonical name from toggl
        if workspace_name is not None:
            workspace = WorkspaceList().find_by_name(workspace_name)
            if workspace == None:
                raise RuntimeError("Workspace '%s' not found." % workspace_name)
            else:
                ws_name = workspace["name"]
        project_name = self._get_project_arg(args, optional=True)
        if project_name is not None:
            project = ProjectList(ws_name).find_by_name(project_name)
            if project == None:
                raise RuntimeError("Project '%s' not found." % project_name)

        start_time = self._get_datetime_arg(args, optional=False)
        duration = self._get_duration_arg(args, optional=True)
        if duration is None:
            stop_time = self._get_datetime_arg(args, optional=False)
            duration = (stop_time - start_time).total_seconds()
        else:
            stop_time = None

        # Create a time entry.
        entry = TimeEntry(
            description=description,
            start_time=start_time,
            stop_time=stop_time,
            duration=duration,
            project_name=project_name,
            workspace_name=workspace_name
        )

        Logger.debug(entry.json())
        entry.add()
        Logger.info('%s added' % description)
        
    def act(self):
        """
        Performs the actions described by the list of arguments in self.args.
        """
        if len(self.args) == 0 or self.args[0] == "ls":
            Logger.info(TimeEntryList())
        elif self.args[0] == "add":
            self._add_time_entry(self.args[1:])
        elif self.args[0] == "clients":
            print(ClientList())
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
            print(WorkspaceList())
        else:
            self.print_help()

    def _show_projects(self, args):
        workspace_name = self._get_workspace_arg(args, optional=True)
        print(ProjectList(workspace_name))

    def _continue_entry(self, args):
        """
        Continues a time entry. args[0] should be the description of the entry
        to restart. If a description appears multiple times in your history,
        then we restart the newest one.
        """
        if len(args) == 0:
            CLI().print_help()
        entry = TimeEntryList().find_by_description(args[0])
        if entry:
            entry.continue_entry()
            Logger.info("%s continued at %s" % (entry.get('description'), 
                DateAndTime().format_time(datetime.datetime.now())))
        else:
            Logger.info("Did not find '%s' in list of entries." % args[0] )

    def _delete_time_entry(self, args):
        """
        Removes a time entry from toggl.
        args must be [ID] where ID is the unique identifier for the time
        entry to be deleted.
        """
        if len(args) == 0:
            CLI().print_help()

        entry_id = args[0]

        for entry in TimeEntryList():
            if entry.get('id') == int(entry_id):
                entry.delete()
                Logger.info("Deleting entry " + entry_id)

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
            return DateAndTime().parse_local_datetime_str(args.pop(0))

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
            return DateAndTime().duration_str_to_seconds( args.pop(0)[1:] )

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
        entry = TimeEntryList().now()

        if entry != None:
            Logger.info(str(entry))
        else:
            Logger.info("You're not working on anything right now.")

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
        	start_time = DateAndTime().now() - datetime.timedelta(seconds=duration)
    	else:
        	start_time = self._get_datetime_arg(args, optional=True)


        # Create the time entry.
        entry = TimeEntry(
            description=description,
            start_time=start_time,
            project_name=project_name,
            workspace_name=workspace_name
        )
        entry.start()
        Logger.debug(entry.json())
        friendly_time = DateAndTime().format_time(DateAndTime().parse_iso_str(entry.get('start')))
        Logger.info('%s started at %s' % (description, friendly_time))
        
    def _stop_time_entry(self, args):
        """
        Stops the current time entry. 
        args contains an optional end time.
        """

        entry = TimeEntryList().now()
        if entry != None:
            if len(args) > 0:
                entry.stop(DateAndTime().parse_local_datetime_str(args[0]))
            else:
                entry.stop()

            Logger.debug(entry.json())
            friendly_time = DateAndTime().format_time(DateAndTime().parse_iso_str(entry.get('stop')))
            Logger.info('%s stopped at %s' % (entry.get('description'), friendly_time))
        else:
            Logger.info("You're not working on anything right now.")

if __name__ == "__main__":
    CLI().act()
    sys.exit(0)
