#!/usr/bin/python
"""
toggl.py

Created by Robert Adams on 2012-04-19.
Last modified: 2014-10-13
Copyright (c) 2012 D. Robert Adams. All rights reserved.
Modified for toggl API v8 by Beau Raines
"""

#############################################################################
### Configuration Section                                                 ###
###

# How do you log into toggl.com?
AUTH = ('', '')

# Do you want to ignore starting times by default?
IGNORE_START_TIMES = False

# Command to visit toggl.com
VISIT_WWW_COMMAND = "open http://www.toggl.com"

###                                                                       ###
### End of Configuration Section                                          ###
#############################################################################

import datetime
import iso8601
import json
import optparse
import os
import pytz
import requests
import sys
import time
import urllib
import ConfigParser
from dateutil.parser import *

TOGGL_URL = "https://www.toggl.com/api/v8"

def add_time_entry(args):
    """
    Creates a completed time entry.
    args should be: ENTRY [@PROJECT] DURATION
    """
    
    # Make sure we have an entry description.
    if len(args) < 2:
        global parser
        parser.print_help()
        return 1
    entry = args[0]
    args = args[1:] # strip of the entry
    
    # See if we have a @project.
    if len(args) == 2:
	project_name = find_project(args[0][1:])
        args = args[1:] # strip off the project
    
    # Get the duration.
    duration = parse_duration(args[0])
    
    # Create the JSON object, or die trying.
    data = create_time_entry_json(entry, project_name, duration)
    if data == None:
        return 1
    
    if options.verbose:
        print json.dumps(data)
    
    # Send the data.
    headers = {'content-type': 'application/json'}
    r = requests.post("%s/time_entries" % TOGGL_URL, auth=AUTH,
        data=json.dumps(data), headers=headers)
    r.raise_for_status() # raise exception on error
    
    return 0

def create_time_entry_json(description, project_name=None, duration=0):
    """Creates a basic time entry JSON from the given arguments
       project_name should not have the '@' prefix.
       duration should be an integer seconds.
    """
    
    # See if we have a @project.
    project_id = None
    if project_name != None:
        # Look up the project from toggl to get the id.
        projects = get_projects()
        for project in projects:
            if project['name'] == project_name:
                project_id = project['id']
                break
        if project_id == None:
            print >> sys.stderr, "Project not found '%s'" % project_name
            return None
    
    # If duration is 0, then we calculate the number of seconds since the
    # epoch.
    if duration == 0:
        duration = 0-time.time()

    tz = pytz.timezone(toggl_cfg.get('options', 'timezone'))
    
    # Create JSON object to send to toggl.
    data = { 'time_entry' : \
	{ 'duration' : duration,
          'billable' : False,
	  'start' :  tz.localize(datetime.datetime.now()).isoformat(),
          'description' : description,
          'created_with' : 'toggl-cli',
        }
    }
    if project_id != None:
        data['time_entry']['pid'] = project_id 
    
    return data

def elapsed_time(seconds, suffixes=['y','w','d','h','m','s'], add_s=False, separator=' '):
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

def get_current_time_entry():
    """Returns the current time entry JSON object, or None."""
    response = get_time_entry_data()
    
    for entry in response:
        if int(entry['duration']) < 0:
            return entry
    
    return None

def get_projects():
    """Fetches the projects as JSON objects."""
    
    # Look up default workspace
    user = get_user()
    wid = user['data']['default_wid']
    url = "%s/workspaces/%s/projects" % (TOGGL_URL,wid)
    global options
    if options.verbose:
        print url
    r = requests.get(url, auth=AUTH)
    r.raise_for_status() # raise exception on error
    return json.loads(r.text)

def get_clients():
    """Fetches the clients as JSON objects."""
    # Look up default workspace
    url = "%s/clients" % (TOGGL_URL)
    global options
    if options.verbose:
        print url
    r = requests.get(url, auth=AUTH)
    r.raise_for_status() # raise exception on error
    return json.loads(r.text)

def get_user():
    """Fetches the user as JSON objects."""
    
    url = "%s/me" % (TOGGL_URL)
    global options
    if options.verbose:
        print url
    r = requests.get(url, auth=AUTH)
    r.raise_for_status() # raise exception on error
    return json.loads(r.text)

def get_time_entry_data():
    """Fetches time entry data and returns it as a Python array."""

    # Construct the start and end dates. 
    #Toggl can accept these in local tz, but must be IS08601 formatted
    tz = pytz.timezone(toggl_cfg.get('options', 'timezone'))

    today = datetime.datetime.now(tz)
    today_at_midnight = today.replace(hour=23, minute=59, second=59, microsecond = 0)
    today_at_midnight = today_at_midnight.isoformat('T')
        
    yesterday = today - datetime.timedelta(days=1)
    yesterday_at_midnight = datetime.datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0)
    yesterday_at_midnight = tz.localize(yesterday_at_midnight)
    yesterday_at_midnight = yesterday_at_midnight.isoformat('T')

    # Fetch the data or die trying.
    url = "%s/time_entries?start_date=%s&end_date=%s" % \
        (TOGGL_URL, urllib.quote(str(yesterday_at_midnight)), urllib.quote(str(today_at_midnight)))
    global options
    if options.verbose:
        print url
    r = requests.get(url, auth=AUTH)
    r.raise_for_status() # raise exception on error
    
    return json.loads(r.text)

def list_current_time_entry():
    """Shows what the user is currently working on (duration is negative)."""
    entry = get_current_time_entry()

    if entry != None:
        projects = get_projects()
	# Lookup the project if it exists
       	project_name = "No project"
    	if 'pid' in entry:
   	    for project in projects:
       	        if entry['pid'] == project['id']:
                    entry['project_name'] = '@' + project['name']
        print_time_entry(entry)
    else:
        print "You're not working on anything right now."
    
    return 0

def list_clients():
    """List all clients."""
    response = get_clients()
    for client in response:
        print "@%s" % (client['name'])
    return 0

def list_projects():
    """List all projects."""
    response = get_projects()
    clients = get_clients()
    for project in response:
        client_name = "No Client"
    	if 'cid' in project:
	   for client in clients:
	       if project['cid'] == client['id']:
	           client_name = client['name']
        print "@%s - %s" % (project['name'], client_name)
    return 0

def find_project(proj):
    """Find a project given the unique prefix of the name"""
    response = get_projects()
    for project in response:
        if project['name'].startswith(proj):
		return project['name']
    print "Could not find project!"
    sys.exit(1)

def find_project_by_id(id):
    """Find a project given the project id"""
    response = get_projects()
    for project in response:
        if project['id'] ==id:
		return project['name']
    print "Could not find project!"
    return None

def list_time_entries():
	"""Lists all of the time entries from yesterday and today along with
	   the amount of time devoted to each.
	"""

	# Get an array of objects of recent time data.
	response = get_time_entry_data()
	projects = get_projects()

	# Sort the time entries into buckets based on "Month Day" of the entry.
	days = { }
	tz = pytz.timezone(toggl_cfg.get('options', 'timezone'))
	for entry in response:
		start_time = iso8601.parse_date(entry['start']).astimezone(tz).strftime("%b %d")
		if start_time not in days:
			days[start_time] = []
		days[start_time].append(entry)
		# Lookup the project if it exists
        	entry['project_name'] = "No project"
    		if 'pid' in entry:
	   	    for project in projects:
	       	        if entry['pid'] == project['id']:
	                    entry['project_name'] = '@' + project['name']

	# For each day, print the entries, then sum the times.
	for date in sorted(days.keys()):
		print date
		duration = 0
		for entry in days[date]:
			print "  ",
			duration += print_time_entry(entry)
		print "   (%s)" % elapsed_time(int(duration))

	return 0

def parse_duration(str):
    """Parses a string of the form [[Hours:]Minutes:]Seconds and returns
       the total time in seconds as an integer.
    """
    elements = str.split(':')
    duration = 0
    if len(elements) == 3:
        duration += int(elements[0]) * 3600
        elements = elements[1:]
    if len(elements) == 2:
        duration += int(elements[0]) * 60
        elements = elements[1:]
    duration += int(elements[0])
    
    return duration
        
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
        is_running = '* '
        e_time = time.time() + int(entry['duration'])
    e_time_str = " %s" % elapsed_time(int(e_time), separator='')
    
    if options.verbose:
        print "%s%s%s%s [%s]" % (is_running, entry['description'] if 'description' in entry else "", entry['project_name'], e_time_str, entry['id'])
    else:
        print "%s%s%s%s" % (is_running, entry['description'] + " " if 'description' in entry else "", entry['project_name'], e_time_str)

    return e_time

def delete_time_entry(args):
    if len(args) == 0:
        global parser
        parser.print_help()
        return 1

    entry_id = args[0]

    response = get_time_entry_data()

    for entry in response:
	if str(entry['id']) == entry_id:
            print "Deleting entry " + entry_id

            headers = {'content-type': 'application/json'}
            r = requests.delete("%s/time_entries/%s" % (TOGGL_URL, entry_id), auth=AUTH,
                data=None, headers=headers)
            r.raise_for_status() # raise exception on error

    return 0

def start_time_entry(args):
    """
       Starts a new time entry.
       args should be: ENTRY [@PROJECT]
    """
    
    global toggl_cfg
    # Make sure we have an entry description.
    if len(args) == 0:
        global parser
        parser.print_help()
        return 1
    entry = args[0]
    args = args[1:] # strip off the entry description
    
    # See if we have a @project.
    project_name = None
    if len(args) >= 1 and args[0][0] == '@':
	project_name = find_project(args[0][1:])
        args = args[1:] # strip off the project

    # Create JSON object to send to toggl.
    data = create_time_entry_json(entry, project_name, 0)

    if len(args) == 1:
	tz = pytz.timezone(toggl_cfg.get('options', 'timezone'))
	dt = parse(args[0])
	st = tz.localize(dt)
        data['time_entry']['start'] = st.isoformat()
	data['time_entry']['duration'] = 0 - int(dt.strftime('%s'))
    
    if options.verbose:
        print json.dumps(data)
    
    headers = {'content-type': 'application/json'}
    r = requests.post("%s/time_entries" % TOGGL_URL, auth=AUTH,
        data=json.dumps(data), headers=headers)
    r.raise_for_status() # raise exception on error
    
    return 0

def stop_time_entry(args=None):
    """Stops the current time entry (duration is negative)."""
    global toggl_cfg

    entry = get_current_time_entry()
    if entry != None:
        # Get the start time from the entry, converted to UTC.
        start_time = iso8601.parse_date(entry['start']).astimezone(pytz.utc)

        if args != None and len(args) == 1:
	    tz = pytz.timezone(toggl_cfg.get('options', 'timezone'))
	    stop_time = tz.localize(parse(args[0])).astimezone(pytz.utc)
        else:
            # Get stop time(now) in UTC.
            stop_time = datetime.datetime.now(pytz.utc)

        # Create the payload.
        data = { 'time_entry' : entry }
        data['time_entry']['stop'] = stop_time.isoformat()
        data['time_entry']['duration'] = (stop_time - start_time).seconds

        url = "%s/time_entries/%d" % (TOGGL_URL, entry['id'])

        global options
        if options.verbose:
            print url

        headers = {'content-type': 'application/json'}
        r = requests.put(url, auth=AUTH, data=json.dumps(data), headers=headers)
        r.raise_for_status() # raise exception on error
    else:
        print >> sys.stderr, "You're not working on anything right now."
        return 1

    return 0

def visit_web():
	os.system(VISIT_WWW_COMMAND)	

def create_default_cfg():
    cfg = ConfigParser.RawConfigParser()
    cfg.add_section('auth')
    cfg.set('auth', 'username', 'user@example.com')
    cfg.set('auth', 'password', 'secretpasswd')
    cfg.add_section('options')
    cfg.set('options', 'ignore_start_times', 'False')
    cfg.set('options', 'timezone', 'UTC')
    with open(os.path.expanduser('~/.togglrc'), 'w') as cfgfile:
        cfg.write(cfgfile)
    os.chmod(os.path.expanduser('~/.togglrc'), 0600)

def main(argv=None):
    """Program entry point."""
    
    global toggl_cfg
    toggl_cfg = ConfigParser.ConfigParser()
    if toggl_cfg.read(os.path.expanduser('~/.togglrc')) == []:
	    create_default_cfg()
	    print "Missing ~/.togglrc. A default has been created for editing."
	    return 1

    global AUTH, IGNORE_START_TIMES
    AUTH = (toggl_cfg.get('auth', 'username').strip(), toggl_cfg.get('auth', 'password').strip())
    IGNORE_START_TIMES = toggl_cfg.getboolean('options', 'ignore_start_times')

    # Override the option parser epilog formatting rule.
    # See http://stackoverflow.com/questions/1857346/python-optparse-how-to-include-additional-info-in-usage-output
    optparse.OptionParser.format_epilog = lambda self, formatter: self.epilog
    
    global parser, options
    parser = optparse.OptionParser(usage="Usage: %prog [OPTIONS] [ACTION]", \
        epilog="\nActions:\n"
        "  add ENTRY [@PROJECT] DURATION\t\tcreates a completed time entry\n"
        "  ls\t\t\t\t\tlist recent time entries\n"
        "  rm ID\t\t\t\t\tdelete a time entry by id\n"
        "  now\t\t\t\t\tprint what you're working on now\n"
        "  projects\t\t\t\tlists all projects\n"
        "  clients\t\t\t\tlists all clients\n"
        "  start ENTRY [@PROJECT] [DATETIME]\tstarts a new entry\n"
        "  stop [DATETIME]\t\t\tstops the current entry\n"
	"  www\t\t\t\t\tvisits toggl.com\n"
        "\n"
        "  DURATION = [[Hours:]Minutes:]Seconds\n")
    parser.add_option("-v", "--verbose",
                          action="store_true", dest="verbose", default=False,
                          help="print debugging output")
    parser.add_option("-i", "--ignore",
                        action="store_true", dest="ignore_start_and_stop", default=IGNORE_START_TIMES,
                        help="ignore starting and ending times")
    parser.add_option("-n", "--no_ignore",
                        action="store_false", dest="ignore_start_and_stop", default=IGNORE_START_TIMES,
                        help="don't ignore starting and ending times")
    (options, args) = parser.parse_args()
    
    if len(args) == 0 or args[0] == "ls":
        return list_time_entries()
    elif args[0] == "add":
        return add_time_entry(args[1:])
    elif args[0] == "now":
        return list_current_time_entry()
    elif args[0] == "projects":
        return list_projects()
    elif args[0] == "clients":
        return list_clients()
    elif args[0] == "start":
        return start_time_entry(args[1:])
    elif args[0] == "stop":
	if len(args) > 1:
            return stop_time_entry(args[1:])
        else:
	    return stop_time_entry()
    elif args[0] == "www":
        return visit_web()
    elif args[0] == "rm":
	return delete_time_entry(args[1:])
    else:
        parser.print_help()
        return 1

if __name__ == "__main__":
	sys.exit(main())
