Overview
--------

toggl-cli is a command-line interface for toggl.com.

It certainly does not implement the full toggl API, but rather some core
functions. The goal is to make using toggl quicker and more efficient for those
already familiar with command-line tools.

toggl-cli is written in Python and uses version 8 of the [toggl
API](https://github.com/toggl/toggl_api_docs) (thanks to beauraines for the
help).

Requirements
------------

* iso8601 module
* pytz module

Configuration
-------------

Upon first running the program, a configuration file `~/.togglrc` will be
automatically created. 

1. Update that file with your toggl username and password.
2. Update the timezone entry (e.g. US/Pacific).

Limitations
-----------

* When creating a time entry for a given project, the project must already
  exist.
* Project users, tasks, tags, and users aren't supported.
* Only the default workspace is supported.

Roadmap
-------

See the [issues tracker](https://github.com/drobertadams/toggl-cli/issues)

Usage
-----
	Usage: toggl [OPTIONS] [ACTION]

	Options:
	  -h, --help       show this help message and exit
	  -v, --verbose    print debugging output

	Actions:
	  add DESCR [@PROJECT] START_DATETIME ('d'DURATION | END_DATETIME)
		creates a completed time entry
	  clients
		lists all clients
	  continue DESCR
		restarts the given entry
	  ls
		list recent time entries
	  now
		print what you're working on now
	  projects
		lists all projects
	  rm ID
		delete a time entry by id
	  start DESCR [@PROJECT] [DATETIME]
		starts a new entry
	  stop [DATETIME]
		stops the current entry
	  www
		visits toggl.com

	  DURATION = [[Hours:]Minutes:]Seconds
