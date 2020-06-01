# Command Line Interface

Upon installation of Toggl CLI with pip, it exposes the command line interface under binary `toggl`. 

This section will explain the high-level overview of the CLI and several features. For detailed 
overview of all options for each command, please use `--help` parameter.

!!! warning "Virtualenv and other modifications of Python environment"
    As the `toggl` binary depends on the Python's environment, any action which would modify this environment, such as
    usage of virtualenv etc. might disable access to this binary. It depends on which environment you have installed `toggl` in.
    
### Commands overview

The CLI is designed to have several sub-commends which each corresponds to adequate section of the API. Here is presented 
brief overview of the hierarchy.

```
toggl
├── add --- adds new time entry
├── clients
│   ├── add
│   ├── get
│   ├── ls
│   ├── rm
│   └── update
├── config
│   ├── timezone --- sets/display timezone setting
│   ├── workspace --- sets/display default workspace setting
│   └── completion
│       ├── show --- displays what will be added to your shell's rc file
│       └── install --- enable commands completion for your shell
├── continue --- continue existing/last time entry
├── goal --- tracks today's time until your goal is reached
├── ls --- lists last time entries
├── now --- show/update currently runnig time entry
├── project_users --- list all project users in workspace
├── projects
│   ├── add
│   ├── get
│   ├── ls
│   ├── rm
│   ├── update
│   └── users
│       ├── add
│       ├── ls
│       ├── rm
│       └── update
├── rm --- delete a time entry
├── start --- starts new time entry
├── stop --- stops running time entry
├── sum --- shows summary of totally tracked time based on days
├── tasks
│   ├── add
│   ├── get
│   ├── ls
│   ├── rm
│   └── update
├── tags
│   ├── add
│   ├── ls
│   ├── rm
│   └── update
├── users
│   ├── get
│   ├── ls
│   └── signup --- creates new user
├── workspaces
│   ├── get
│   ├── ls
│   └── users
│       ├── invite --- invites user into the current workspace
│       ├── ls
│       ├── rm
│       └── update
└── www --- opens web client
``` 

### Themes

Toggl CLI supports themes in order to be readable in all terminal settings. You can configure it as part of config file
using `theme` option. The possible values are:

 - `plain` for plain theme without any colors
 - `light` for light based theme
 - `dark` for dark based theme

### Shell completion

Toggl CLI supports commands/options completion for `bash`, `zsh`, `PowerShell` and `fish` shells. 

To enable the completion run `toggl config completion install`. 

This command will install completion based on your current shell, it mostly consist of adding 
`_TOGGL_COMPLETE` variable to your `rc` file. If you want to inspect details you can
run `toggl config completion show`.

### Date/time formats

Important part of the CLI is parsing of times & dates. Toggl CLI uses in background of `dateutil` library and it best-effort
function `dateutil.parse()`. This function aims to guess the format of your time or date on best-effort bases. 

It is possible to influence behaviour of this parser through `day_first` and `year_first` settings in config file. See 
[possible settings](index.md#possible-settings).

Examples:

```
10:10 ==> <current date> 10:10
14:10 ==> current date> 14:10
2:10 PM ==> current date> 14:10

Nov 12 10:11 AM ==> <current year>-11-12 10:11

# For only day/month dates the first is always day and second is always month
12.11 10:11 ==> <current year>-11-12 10:11  
11.12 10:11 ==> <current year>-12-11 10:11

# For ful date (day/month/year) the day_first/year_first setting is applied
12.11.18 10:11 ==> 2018-12-11 10:11
12.11.18 10:11 ==> 2018-11-12 10:11 # When day_first=True
12.11.18 10:11 ==> 2012-11-18 10:11 # When year_first=True
```

More examples can be found at [pendulum's documentation](https://pendulum.eustace.io/docs/#rfc-3339)

### Duration formats

Another important part of the CLI is duration syntax for specifying time entries durations if desired. 
Example: 5h2m10s - 5 hours 2 minutes 10 seconds.

Syntax is as follow:

* 'd' : days
* 'h' : hours
* 'm' : minutes
* 's' : seconds


### Environmental variables

It is possible to specify several options for the CLI commands through environmental variables. This can for example nicely
play out for directory specific settings (for example for projects) with [direnv](https://github.com/direnv/direnv) tool. 
Generally this mechanism is available for commands that create new entities. Values specified through this way have
priority over config values.

You can see which options can be specified in command's help page where at the option's help is
used `(ENV: <name of variable>)` syntax. Bellow you can see general overview of the variables:

* **TOGGL_CONFIG** - Defines which config file should be used. Should be absolute path. By default `~/.togglrc` is used.
* **TOGGL_WORKSPACE** - Defines workspace to be used for the command, can be ID or Name of the Workspace.
* **TOGGL_TASK** - Defines task to be used, can be ID or Name of the Task.
* **TOGGL_PROJECT** - Defines project to be used, can be ID or Name of the Project.
* **TOGGL_API_TOKEN** - Defines Toggl's account which will be used for the API calls.
* **TOGGL_USERNAME** - Defines Toggl's account which will be used for the API calls.
* **TOGGL_PASSWORD** - Defines Toggl's account which will be used for the API calls.