Overview
--------

toggl-cli is a command-line interface for toggl.com.

It certainly does not implement the full toggl API, but rather those functions
core functions. The goal is to make using toggl quicker and more
efficient for those already familiar with command-line tools.

toggl-cli is written in Python and uses version 8 of the [toggl API](https://github.com/toggl/toggl_api_docs).

This is forked from [drobertadams/toggl-cli](https://github.com/drobertadams/toggl-cli).

The core code is as drobertadams wrote it, but upgraded to v8.


Requirements
------------

* iso8601 module
* pytz module

Configuration
-------------

Upon first running the program, a configuration file ~/.togglrc will be automatically created. 

1. Update that file with your API token and the password "api_token". Your API token can be found under "My Profile" in your toggl account.
2. Update the timezone entry (e.g. US/Pacific)

Limitations
-----------

* When creating a time entry for a given project, the project must already
  exist.
* Project users, tasks, tags, and users aren't supported.
* Only the default workspace is supported.
* Adding and removing clients is not supported, however, I would like to display clients.

Roadmap
-------

See the [issues tracker](https://github.com/beauraines/toggl-cli)
