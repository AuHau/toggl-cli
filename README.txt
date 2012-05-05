Overview
--------

toggl-cli is a command-line interface for toggl.com.

It certainly does not implement the full toggl API, but rather those functions
that I use all the time. The goal is to make using toggl quicker and more
efficient for those already familiar with command-line tools.

toggl-cli is written in Python and uses version 6 of the toggl API.

There's another toggl CLI at https://github.com/joequery/Toggl-CLI, but I
dislike CLIs with menus. This one is modeled after 
[Todo.txt](http://todotxt.com/). Also, this one is state-less.

Requirements
------------

* iso8601 module
* pytz module

Configuration
-------------

Put your authentication token at the top of the file.

Limitations
-----------

* When creating a time entry for a given project, the project must already
  exist.
* Clients, workspaces, project users, tasks, tags, and users aren't supported,
  simply because I don't use these features. I only use tasks and projects.
