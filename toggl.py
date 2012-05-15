#!/usr/bin/env python
"""
toggl.py

Created by Robert Adams on 2012-04-19.
Copyright (c) 2012 D. Robert Adams. All rights reserved.
"""

#############################################################################
### Configuration Section                                                 ###
###   
# How do you log into toggl.com?
AUTH = ('YOUR_KEY_HERE', 'api_token')
# Do you want to ignore starting times by default?
IGNORE_START_TIMES = True   
###                                                                       ###
### End of Configuration Section                                          ###
#############################################################################

import datetime
import iso8601
import json
import optparse
import pytz
import requests
import sys
import time
import urllib

TOGGL_URL = "https://www.toggl.com/api/v6"

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
        
    for entry in response['data']:
        if int(entry['duration']) < 0:
            return entry
            
    return None
                
def get_projects():
    """Fetches the projects as JSON objects."""

    url = "%s/projects.json" % TOGGL_URL
    global options
    if options.verbose:
        print url
    r = requests.get(url, auth=AUTH)
    r.raise_for_status() # raise exception on error
    return json.loads(r.text)
        
def get_time_entry_data():
    """Fetches time entry data and returns it as a Python array."""
    
    # Construct the start and end dates. Toggl seems to want these in UTC.
    today = datetime.datetime.now(pytz.utc)
    today_at_midnight = today.replace(hour=23, minute=59, second=59)
    
    yesterday = today - datetime.timedelta(days=1)
    yesterday_at_midnight = datetime.datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0)

    # Fetch the data or die trying.
    url = "%s/time_entries.json?start_date=%s&end_date=%s" % \
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
        print_time_entry(entry)
    else:
        print "You're not working on anything right now."
                
    return 0

def list_projects():
    """List all projects."""
    response = get_projects()
    for project in response['data']:
        print "@%s" % project['name']
    return 0
    
def list_time_entries():
    """Lists all of the time entries from yesterday and today along with
       the amount of time devoted to each.
    """
    response = get_time_entry_data()

    for entry in response['data']:
        print_time_entry(entry)
    return 0
    
def print_time_entry(entry):
    """Utility function to print a time entry object."""
    
    # If the duration is negative, the entry is currently running so we 
    # have to calculate the duration by adding the current time.
    is_running = ''
    if entry['duration'] > 0:
        e_time = entry['duration']
    else:
        is_running = '* '
        e_time = time.time() + int(entry['duration'])
    e_time = " %s" % elapsed_time(int(e_time), separator='')
        
    # Get the project name (if one exists).
    project_name = ''
    if 'project' in entry:
        project_name = " @%s" % entry['project']['name']   
        
    print "%s%s%s%s" % (is_running, entry['description'], project_name, e_time)
        
def start_time_entry(args):
    """
       Starts a new time entry. args is the remaining command-line arguments
       after the "start" action. It should be the time entry description
       and an optional project with a '@' prefix.
    """
    
    # Make sure we have an entry description.
    if len(args) == 0:
        global parser
        parser.print_help()
        return 1
    entry = args[0]
    
    # See if we have a @project.
    project_id = None
    if len(args) == 2 and args[1][0] == '@':
        project_name = args[1][1:]
        # Look up the project from toggl to get the id.
        projects = get_projects()
        project_id = None
        for project in projects['data']:
            if project['name'] == project_name:
                project_id = project['id']
                break
        if project_id == None:
            print >> sys.stderr, "Project not found '%s'" % project_name        
    
    # Create JSON object to send to toggl.
    data = { 'time_entry' : \
        { 'duration' : 0-time.time(),    # toggl expects 0-current_time
          'billable' : True, 
          'start' : datetime.datetime.utcnow().isoformat(), 
          'description' : entry, 
          'created_with' : 'toggl-cli',
          'ignore_start_and_stop' : options.ignore_start_and_stop
        } 
    }
    if project_id != None:
        data['time_entry']['project'] = { 'id' : project_id }
    headers = {'content-type': 'application/json'}
    
    if options.verbose:
        print json.dumps(data)
    
#    r = requests.post("%s/time_entries.json" % TOGGL_URL, auth=AUTH,
#        data=json.dumps(data), headers=headers)
#    r.raise_for_status() # raise exception on error
    
    return 0
    
def stop_time_entry():
    """Stops the current time entry (duration is negative)."""
    entry = get_current_time_entry()
    if entry != None:
        
        # Get the start time from the entry, converted to UTC.
        start_time = iso8601.parse_date(entry['start']).astimezone(pytz.utc)
        
        # Get stop time(now) in UTC.
        stop_time = datetime.datetime.now(pytz.utc)
        
        # Create the payload.
        data = { 'time_entry' : entry }
        data['time_entry']['stop'] = stop_time.isoformat()
        data['time_entry']['duration'] = (stop_time - start_time).seconds
         
        url = "%s/time_entries/%d.json" % (TOGGL_URL, entry['id'])
        
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
    
def main(argv=None):
    """Program entry point."""
        
    # Override the option parser epilog formatting rule.
    # See http://stackoverflow.com/questions/1857346/python-optparse-how-to-include-additional-info-in-usage-output
    optparse.OptionParser.format_epilog = lambda self, formatter: self.epilog
    
    global parser, options
    parser = optparse.OptionParser(usage="Usage: %prog [OPTIONS] [ACTION]", \
        epilog="\nActions:\n"
        "  ls\t\t\t\tlist recent time entries\n"
        "  now\t\t\t\tprint what you're working on now\n"
        "  projects\t\t\tlists all projects\n"
        "  start ENTRY [@PROJECT]\tstarts a new entry\n"
        "  stop\t\t\t\tstops the current entry\n")
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
    elif args[0] == "now":
        return list_current_time_entry()
    elif args[0] == "projects":
        return list_projects()
    elif args[0] == "start":
        return start_time_entry(args[1:])
    elif args[0] == "stop":
        return stop_time_entry()
    else:
        parser.print_help()
        return 1

if __name__ == "__main__":
	sys.exit(main())
