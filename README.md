Overview
--------

toggl-cli is a command-line interface for toggl.com.

It certainly does not implement the full toggl API, but rather some
core functions. The goal is to make using toggl quicker and more
efficient for those already familiar with command-line tools.

toggl-cli is written in Python and uses version 8 of 
the [toggl API](https://github.com/toggl/toggl_api_docs).

Requirements
------------

* iso8601 module
* pytz module

Configuration
-------------

Upon first running the program, a configuration file ~/.togglrc will be automatically created. 

1. Update that file with your API token as the username, and the string "api_token" (without quotes) 
   as the password. Your API token can be found under "My Profile" in your toggl account.
2. Update the timezone entry (e.g. US/Pacific)

Limitations
-----------

* When creating a time entry for a given project, the project must already exist.
* Project users, tasks, tags, and users aren't supported.
* Only the default workspace is supported.

Roadmap
-------

See the [issues tracker](https://github.com/drobertadams/toggl-cli/issues)
