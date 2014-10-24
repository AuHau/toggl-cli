#!/usr/bin/python
"""
toggl.py

Created by Robert Adams on 2012-04-19.
Copyright (c) 2012 D. Robert Adams. All rights reserved.
Modified for toggl API v8 by Beau Raines
"""

#############################################################################
### Configuration Section                                                 ###
###

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

AUTH = ('', '') # How do you log into toggl.com? Read from ~/.togglrc
TOGGL_URL = "https://www.toggl.com/api/v8"

#----------------------------------------------------------------------------
def add_time_entry(args):
    """
    Creates a completed time entry.
    args should be: DESCR [@PROJECT] START_DATE_TIME 
        'd'DURATION | END_DATE_TIME
    """
    
    # Make sure we have an entry description.
    if len(args) < 2:
        global parser
        parser.print_help()
        return 1
    entry = args[0]
    args = args[1:] # strip of the entry
    
    # See if we have a @project.
    project_name = None
    if len(args) >= 1 and args[0][0] == '@':
	project_name = find_project(args[0][1:])
        args = args[1:] # strip off the project

    # Create the JSON object, or die trying.
    duration = 0 
    data = create_time_entry_json(entry, project_name, duration)
    if data == None:
        return 1

    #Get start time
    tz = pytz.timezone(toggl_cfg.get('options', 'timezone')) 
    dt = parse(args[0])
    start_time = tz.localize(dt)
    st = start_time.isoformat()
    args = args[1:] # strip off the time
    
    #Update the start time in the JSON object
    data['time_entry']['start'] = st
    
    # Check to see if duration passed.
    if len(args) >= 1 and args[0][0] == 'd':
    	duration = parse_duration(args[0][1:])
	#Update the duation in the JSON object
        data['time_entry']['duration'] = duration
    elif len(args) >= 1:
	dt = parse(args[0])
	end_time = tz.localize(dt)
	et = end_time.isoformat()
	#Update the stop time in the JSON object
    	data['time_entry']['stop'] = et
	#Update the duration in the JSON object
	duration = (end_time - start_time).seconds
	data['time_entry']['duration'] = duration
    else:
        print 'Must specifiy duration or end time'
	return 1

    if options.verbose:
        print json.dumps(data)
    
    # Send the data.
    headers = {'content-type': 'application/json'}
    r = requests.post("%s/time_entries" % TOGGL_URL, auth=AUTH,
        data=json.dumps(data), headers=headers)
    r.raise_for_status() # raise exception on error
    
    return 0

#----------------------------------------------------------------------------
def continue_entry(args):
    """Continues a time entry. args[0] should be the description of the entry
    to restart. Assumes that the entry appears in the list returned by
    get_time_entry_data()."""

    if len(args) == 0:
        global parser
        parser.print_help()
        return 1

    description = args[0]

    entries = get_time_entry_data()

    # There may be multiple entries with the same description. We restart
    # the most recent one by iterating through the responses backwards
    # (newest to oldest), and restart the first one we find.
    for entry in reversed(entries):
	if str(entry['description']) == description:

            # Check when the entry was started, today or previously?
            tz = pytz.timezone(toggl_cfg.get('options', 'timezone'))
            start_time = iso8601.parse_date(entry['start']).astimezone(tz)
            #print start_time
            #print midnight()
            #print start_time < midnight()
            if start_time <= midnight():
                # If the entry was from a previous day, then we simply start
                # a new entry.
                print "Continuing entry '%s' from before." % description
                start_time_entry( [description, '@%s' % find_project_by_id(entry['pid']) ] )
                return 0
            else:
                print "Continuing entry '%s' from today." % description

                # To continue an entry, set duration to 
                # 0-(current_time-duration).
                entry['duration'] = 0-(time.time()-int(entry['duration']))
                entry['duronly'] = True # ignore start/stop times from now on

                # Send the data.
                headers = {'content-type': 'application/json'}
                r = requests.put("%s/time_entries/%s" % (TOGGL_URL, entry['id']), 
                    auth=AUTH, 
                    data='{"time_entry":%s}' % json.dumps(entry), headers=headers)
                r.raise_for_status() # raise exception on error
                return 0

    print "Did not find '%s' in list of entries." % description
    return 1

#----------------------------------------------------------------------------
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

#----------------------------------------------------------------------------
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

#----------------------------------------------------------------------------
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

#----------------------------------------------------------------------------
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
    
#----------------------------------------------------------------------------
def find_project(proj):
    """Find a project given the unique prefix of the name"""
    response = get_projects()
    for project in response:
        if project['name'].startswith(proj):
		return project['name']
    print "Could not find project!"
    sys.exit(1)

#----------------------------------------------------------------------------
def find_project_by_id(id):
    """Find a project given the project id"""
    response = get_projects()
    for project in response:
        if project['id'] ==id:
		return project['name']
    print "Could not find project!"
    return None

#----------------------------------------------------------------------------
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

#----------------------------------------------------------------------------
def get_current_time_entry():
    """Returns the current time entry JSON object, or None."""
    response = get_time_entry_data()
    
    for entry in response:
        if int(entry['duration']) < 0:
            return entry
    
    return None

#----------------------------------------------------------------------------
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

#----------------------------------------------------------------------------
def get_time_entry_data():
    """Fetches time entry data and returns it as a Python array."""

    # Fetch time entries from 00:00:00 yesterday to 23:59:59 today.
    url = "%s/time_entries?start_date=%s&end_date=%s" % \
        (TOGGL_URL, urllib.quote(yesterday().isoformat('T')), \
        urllib.quote(last_minute_today().isoformat('T')))

    global options
    if options.verbose:
        print url
    r = requests.get(url, auth=AUTH)
    r.raise_for_status() # raise exception on error
    
    return json.loads(r.text)

#----------------------------------------------------------------------------
def get_user():
    """Fetches the user as JSON objects."""
    
    url = "%s/me" % (TOGGL_URL)
    global options
    if options.verbose:
        print url
    r = requests.get(url, auth=AUTH)
    r.raise_for_status() # raise exception on error
    return json.loads(r.text)

#----------------------------------------------------------------------------
def last_minute_today():
    """
    Returns 23:59:59 today as a localized datetime object.
    """
    tz = pytz.timezone(toggl_cfg.get('options', 'timezone'))
    today = datetime.datetime.now(tz)
    last_minute = today.replace(hour=23, minute=59, second=59, microsecond=0)
    return last_minute

#----------------------------------------------------------------------------
def list_clients():
    """List all clients."""
    response = get_clients()
    for client in response:
        print "@%s" % (client['name'])
    return 0


#----------------------------------------------------------------------------
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

#----------------------------------------------------------------------------
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

#----------------------------------------------------------------------------
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

#----------------------------------------------------------------------------
def midnight():
    """
    Returns 00:00:00 today as a localized datetime object.
    """
    tz = pytz.timezone(toggl_cfg.get('options', 'timezone'))
    today = datetime.datetime.now(tz).date()
    midnight = tz.localize(datetime.datetime.combine(today, datetime.time(0,0)))
    return midnight

#----------------------------------------------------------------------------
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
        is_running = '* '
        e_time = time.time() + int(entry['duration'])
    e_time_str = " %s" % elapsed_time(int(e_time), separator='')
    
    if options.verbose:
        print "%s%s%s%s [%s]" % (is_running, entry['description'] if 'description' in entry else "", entry['project_name'], e_time_str, entry['id'])
    else:
        print "%s%s%s%s" % (is_running, entry['description'] + " " if 'description' in entry else "", entry['project_name'], e_time_str)

    return e_time

#----------------------------------------------------------------------------
def start_time_entry(args):
    """
       Starts a new time entry.
       args should be: DESCR [@PROJECT] [DATETIME]
    """
    
    # Make sure we have an entry description.
    if len(args) == 0:
        global parser
        parser.print_help()
        return 1
    description = args[0]
    args = args[1:] # strip off the description
    
    # See if we have a @project.
    project_name = None
    if len(args) >= 1 and args[0][0] == '@':
	project_name = find_project(args[0][1:])
        args = args[1:] # strip off the project

    # Create JSON object to send to toggl.
    data = create_time_entry_json(description, project_name, 0)

    global toggl_cfg
    if len(args) == 1: # we have a specific start datetime
	tz = pytz.timezone(toggl_cfg.get('options', 'timezone'))
	dt = parse(args[0])
	st = tz.localize(dt)
        data['time_description']['start'] = st.isoformat()
	data['time_description']['duration'] = 0 - int(dt.strftime('%s'))
    
    if options.verbose:
        print json.dumps(data)
    
    headers = {'content-type': 'application/json'}
    r = requests.post("%s/time_entries" % TOGGL_URL, auth=AUTH,
        data=json.dumps(data), headers=headers)
    r.raise_for_status() # raise exception on error
    
    return 0

#----------------------------------------------------------------------------
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

#----------------------------------------------------------------------------
def visit_web():
    os.system(VISIT_WWW_COMMAND)	

#----------------------------------------------------------------------------
def yesterday():
    """
    Returns 00:00:00 yesterday as a localized datetime object.
    """
    tz = pytz.timezone(toggl_cfg.get('options', 'timezone'))
    yesterday = datetime.datetime.now(tz) - datetime.timedelta(days=1)
    yesterday_at_midnight = datetime.datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0)
    yesterday_at_midnight = tz.localize(yesterday_at_midnight)
    return yesterday_at_midnight

#----------------------------------------------------------------------------
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
    elif args[0] == "clients":
        return list_clients()
    elif args[0] == "continue":
        return continue_entry(args[1:])
    elif args[0] == "now":
        return list_current_time_entry()
    elif args[0] == "projects":
        return list_projects()
    elif args[0] == "rm":
	return delete_time_entry(args[1:])
    elif args[0] == "start":
        return start_time_entry(args[1:])
    elif args[0] == "stop":
	if len(args) > 1:
            return stop_time_entry(args[1:])
        else:
	    return stop_time_entry()
    elif args[0] == "www":
        return visit_web()
    else:
        parser.print_help()
        return 1

if __name__ == "__main__":
	sys.exit(main())
